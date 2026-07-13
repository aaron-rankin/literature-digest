# Subtask 13 — Per-term `--limit` (round-robin screening)

**To-do:** new — change `--limit N` so the screening cap applies **per search term**, not globally across an area.
**Decisions:** D1 (folder is source of truth — one `.txt` = one search term), D2 (all sources discover every term), D4 (pipeline owns the crawl window per term).
**Depends on:** 05 (`matched_terms` on `Article` — already merged).

## Problem

`--limit N` currently caps the **area-wide** unseen list with a flat slice:

```python
# pipeline.py:166-173
if limit is not None and len(new_articles) > limit:
    new_articles = new_articles[:limit]
```

Articles are concatenated in term order (`game_model` first → `tracking_data` last), so a small `--limit 15` against 4 terms screens **only the first term's articles**: the run we did on 13 Jul screened 15 game_model papers, 0 spatiotemporal/style_of_play/tracking_data, and the rendered report collapsed to one term section. This makes `--limit` useless for its stated purpose — quick dry runs that exercise the whole report UI.

## Goal

`--limit N` screens **up to N articles per matched search term** within an area. A 4-term area with `--limit 5` screens up to 20 articles (5 × 4), balanced across terms so the report shows all term sections and the LLM stage sees representative content from every query. Global behaviour is preserved by leaving `--limit` unset (screen everything).

## Design decisions

| # | Topic | Decision |
|---|-------|----------|
| Q1 | Semantics | **Per-term cap, additive across terms.** `--limit N` → up to N unseen articles per `Article.matched_terms` bucket within the area. Articles matched by multiple terms count toward each matching bucket's cap (consistent with the report's per-term duplication in subtask 12). |
| Q2 | Sort order within bucket | **Insertion order (fetch order), unchanged.** Do not re-sort; the fetch already returns per-term slices in the order each source emitted them, and dedupe preserves first-seen. Pre-screening sort is a separate concern (subtask 12 sorts by score only for display). |
| Q3 | Balance / round-robin? | **No.** Flat cap per bucket is simpler, deterministic, and surfaces the first N per term — which is what a dry run wants. Round-robin interleaving across terms would change per-article order in the log and is not worth the complexity. |
| Q4 | Truncation / `last_run` advance | **Truncated iff any bucket was capped.** Keep the current rule: if `--limit` actually reduced any term's bucket, mark the run truncated and do **not** advance `last_run` (re-running screens the same set). Only an untruncated full run advances the cursor. |
| Q5 | CLI surface | **Keep `--limit` as a single int; document the new semantics.** No new flag, no `--per-term-limit` / `--total-limit` split. The help string changes from "Cap the number of new articles screened/summarized per area" → "Cap the number of new articles screened **per search term** within each area (dry-run; last_run will not advance if any term is capped)". |
| Q6 | Reporting | **Per-term counts in the run summary log.** After dedupe + limit, print one line per term: `bucket game_model: 75 fetched → 60 unseen → capped to 5`. Keep the existing area totals (`unseen:`, `retained=`, `dropped=`). |
| Q7 | Local mode interaction | **Same rule.** `--local` replays fixtures but `matched_terms` is populated from fixtures; per-term cap applies identically. Useful for previewing the report against all terms from a small fixture slice. |
| Q8 | Zero / negative limits | **Reject early with a clear message** (same as today for `--limit 0`), do not silently screen nothing. Reuse argparse's `type=int` and add a `if limit is not None and limit < 1: error`. |
| Q9 | Tests | **Unit tests for `apply_per_term_limit` + a pipeline-level test with stubbed sources.** No LLM calls; assert per-term bucket sizes, truncation flag, and that the untagged/"Other" bucket (articles with no `matched_terms`) is also capped by the same N (or by `limit_other` if we add it — see Q10). |
| Q10 | Untagged articles | **Cap by the same N under an "Other" bucket.** Articles with no `matched_terms` (legacy / email-only stubs) currently fall through. Put them in a synthetic "Other" bucket capped by the same N so they cannot blow past the cap. (Reuses the bucket shape introduced in `report.build_term_sections` for the report — but pipeline does its own bucketing here for clarity, do not import the report helper into the pipeline.) |

## Proposed implementation

1. **Pure helper: `apply_per_term_limit`** in `pipeline.py` (new function).
   - Input: `articles: list[Article]`, `limit: int | None`.
   - Output: `(kept: list[Article], truncated: bool, per_term_counts: dict[str, tuple[int,int,int]])` where the tuple is `(unseen, capped, kept)`.
   - Preserve insertion order: kept list is `[art for term in term_order for art in bucket[:limit]]` + untagged bucket at the end (so the log/screen stays roughly grouped by term, matching today's behaviour where game_model appears first).
   - `truncated = any(len(bucket) > limit for bucket in buckets)` when `limit is not None`, else `False`.
   - Articles matched by multiple terms appear in **each** matching bucket and consume that bucket's cap (Q1). After slicing per bucket, deduplicate the kept list by DOI / object identity so the screening loop does not screen the same article twice — but record per-term counts *before* dedup so the log accurately reflects "would have screened N for this term".

2. **Wire into `run_area`** (pipeline.py:166).
   - Replace the flat `new_articles[:limit]` slice with `kept, truncated, counts = apply_per_term_limit(new_articles, limit)`.
   - Print per-term bucket lines (Q6) before the screening loop.
   - Keep the existing `if truncated: last_run not advanced` logic untouched — just feed it the new `truncated`.

3. **CLI help string** (cli.py:172).
   - Update the `--limit` help text; no new args.
   - Add the `limit < 1 → 2` guard in `cmd_run` (Q8) returning a clear error before any network call.

4. **Tests** in `tests/test_pipeline_limit.py` (new).
   - `test_apply_per_term_limit_caps_each_bucket`: 4 terms × 10 articles, `limit=3` → 12 kept, 4 buckets all capped to 3, `truncated=True`.
   - `test_apply_per_term_limit_none_screens_all`: `limit=None` → all kept, `truncated=False`.
   - `test_apply_per_term_limit_multi_term_article_counts_in_each_bucket`: one article in two terms counts toward both caps but is deduped in the kept list so it's screened once.
   - `test_apply_per_term_limit_untagged_bucket`: articles with no `matched_terms` go to "Other" and are capped by the same N.
   - `test_pipeline_run_area_caps_per_term_with_stubbed_sources`: stub `ScopusApiSource`/`OpenAlexSource`/`CrossrefSource` to return fixtures tagged with different `matched_terms`, run `run_area` with `--limit 2`, assert no term's retained count exceeds 2 (× categories retained after screening — use a fake screener that passes everything so the cap, not the threshold, is the limiter).
   - `test_cli_rejects_limit_below_one`: `cmd_run` with `--limit 0` returns 2 and prints an error, no pipeline call.

## Files touched

- `src/literature_digest/pipeline.py` — new `apply_per_term_limit`, wire into `run_area`, per-term log lines.
- `src/literature_digest/cli.py` — `--limit` help text + `limit < 1` guard in `cmd_run`.
- `tests/test_pipeline_limit.py` (new) — unit + pipeline-level tests.
- No model / template / report changes (subtask 12 already groups by term; this just feeds it balanced input).

## Acceptance criteria

- [ ] `uv run literature-digest run --area data_science --sources scopus --limit 5 --debug` screens up to 5 articles from **each** of the 4 search terms (≤20 total), and the rendered report has term sections for all 4 terms — not just `game_model`.
- [ ] `--limit` unset screens every unseen article (unchanged behaviour).
- [ ] A run where any term was capped prints "truncated run — last_run left unchanged" and does not advance `last_run`; a full run still advances it.
- [ ] Multi-term articles are screened exactly once even though they count toward each bucket's cap.
- [ ] `--limit 0` and `--limit -3` are rejected before any network call with a clear message.
- [ ] `uv run pytest` green, including `tests/test_pipeline_limit.py`.
- [ ] `uv run ruff check .` clean.