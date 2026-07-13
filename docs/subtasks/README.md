# Subtasks — Implementation Plan

This directory breaks the `docs/To-do.md` items into implementation-ready
subtasks. Each file is one shippable unit of work with its own goal,
dependencies, design decisions (agreed in the grill session), steps, files
touched, and acceptance criteria.

## Decision log (from grill session)

**Paper Finding**
- **D1 — Folder is source of truth.** `data/search_terms/<area>/<term>.txt` is
  authoritative for queries. Areas are auto-discovered from folders. One `.txt`
  = one Scopus query for one sub-topic (search term).
- **D2 — All three sources discover.** Scopus + OpenAlex + Crossref each run
  every query; results are deduped. Free-API queries are best-effort
  approximations of the Scopus query (not exact mirrors) — dedupe + LLM
  screening absorb the noise.
- **D3 — Parse the Scopus subset.** Keep `.txt` as Scopus DSL; parse the
  narrow subset actually used (`TITLE-ABS-KEY`, `TITLE-ABS-KEY-AUTH`, `AND`,
  `OR`, nesting, `PUBYEAR`, `ORIG-LOAD-DATE`) into a term tree. **Reject / flag**
  any DSL outside the subset rather than silently mistranslating it.
  Precedence is **Scopus-native** (`OR` binds tighter than `AND`); `PUBYEAR AFT`
  is **inclusive** (`AFT 2024` → from 2024).
- **D4 — Pipeline owns the crawl window; `PUBYEAR` is authored.** Strip
  `ORIG-LOAD-DATE` from files; the pipeline injects the incremental window
  (`last_run → now` + `lookback_days` overlap) for **every** source, mapped to
  each API's *indexed/created* date. `PUBYEAR` is preserved and translated to
  each API's *publication* date filter.
- **D5 — Thin `areas.yaml` keyed by folder.** `areas.yaml` keeps only
  per-slug metadata (`name`, `threshold`, `enabled`). `keywords` /
  `scopus_query` fields are dropped. Empty folders are skipped. Rewrite areas to
  `data_science` (+ `nutrition` / `performance` when queries are added); retire
  the `sports-nutrition` / `recovery-and-sleep` example areas and stale reports.

**Paper Processing**
- **D6 — Persist scores only.** New `screenings` table (doi, area, run_id,
  model, score, category, rationale, ts) for determinism analysis. Full-article
  history and report-from-DB are out of scope; reports stay HTML.
- **D7 — Group reports by search term.** Within an area report, group retained
  articles under headings per matched search term. Needs `matched_terms` on
  `Article`. HTML only — no PDF for now.
- **D8 — Single model + `--fast` test override.** One model for both stages by
  default; `--fast` swaps in a small local model for test runs. Fast/test runs
  write to a **separate test DB file** so their scores never mix with prod
  scores. Provider (OpenAI / Anthropic / Ollama) is a LiteLLM env concern —
  already supported, just documented.
- **D9 — Determinism eval + borderline flag.** New `screen-eval` command
  re-screens a fixed sample K times (against the test DB) and reports score
  std-dev + category-flip rate. Reports flag articles within ±N points of the
  threshold as "borderline".
- **Answered by code, no work:** model context *is* refreshed per paper
  (screening/summarization are stateless single-message completions at
  `temperature=0`). Nothing is stored in the DB today beyond seen-DOIs / run
  counts / last-run.

**Pipeline**
- **D10 — Defer the container.** Harden the local (launchd) run first:
  robustness, repo cleanup, docs/diagrams. Containerise once logic is stable.
- **D11 — Disk-only delivery.** Pipeline writes HTML to `data/reports/` and
  stops. Email/publish delivery is a future subtask.

## Dependency graph

```
01 search-term loader + thin areas.yaml ─┐
02 scopus-subset parser ─────────────────┼─> 03 query translation + date injection ─> 04 scopus API source
                                         │                                            │
                                         └───────────────> 05 matched-terms + report grouping <┘
06 model tiering (--fast + test DB) ─> 07 screenings persistence ─> 08 determinism eval + borderline
05 matched_terms ──> 11 local offline source mode (fixtures; pairs with 06 --fast)
05 matched_terms + 08 borderline ──> 12 report UI overhaul
05 matched_terms ──> 13 per-term --limit (round-robin screening)
09 robustness + cleanup + docs (spans all)
10 containerisation (deferred)
```

**11 — Local offline source mode.** Replay a fixed fixture set (`data/fixtures/`)
with **no external API calls** (`--local`), optionally with a local Ollama model
(`--fast`), so the LLM/report stages can be iterated without burning Scopus quota
or LLM tokens. Includes a `--capture` step to build fixtures from one real run.

**13 — Per-term `--limit`.** Change `--limit N` from an area-wide cap on unseen
articles to a **per-search-term** cap (up to N articles per `Article.matched_terms`
bucket within an area), so dry runs exercise every term and the report shows all
term sections instead of only the first. Unblocks meaningful `--limit 5` UI dry
runs against live Scopus data.

## Suggested sequencing

1. **01** — foundation: loader + areas reconciliation (unblocks everything).
2. **02** — parser (pure, testable in isolation).
3. **03** — translation + date injection (depends on 02; rewires sources).
4. **04** — real Scopus API source (depends on 03 for query building).
5. **05** — matched-terms plumbing + report grouping.
6. **06 → 07 → 08** — model/persistence/determinism track (largely parallel to 01–05).
7. **11** — local offline mode; buildable right after 05, and a big quality-of-
   life win for debugging 06–08 cheaply. Consider pulling it early.
8. **09** — robustness/cleanup/docs pass once the above lands.
9. **10** — containerise last.
10. **12** — report UI overhaul (after 05 + 08 so grouping and borderline flags
    can be designed in).
11. **13** — per-term `--limit`; pull forward whenever the flat-cap behaviour
    blocks a dry run (pairs well with 12 for verifying the report end-to-end).
