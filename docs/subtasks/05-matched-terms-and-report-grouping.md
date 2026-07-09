# Subtask 05 — Matched-terms tagging + report grouping

**To-do:** Paper Processing → "Report generation … by search term"
**Decisions:** D7
**Depends on:** 03 (per-term source calls), 01 (terms per area)

## Goal

Track which search term(s) surfaced each article, and group each area's HTML
report under per-term headings.

## Design

- Add `matched_terms: list[str]` to `Article` (`models.py`), default `[]`.
- Because sources now run **per term**, each fetch tags its results with the
  originating `term_name` before dedupe.
- `Deduper.dedupe` must **merge** `matched_terms` (and existing `sources`) when
  collapsing duplicates — an article found via `game_model` on Scopus and
  `tracking_data` on OpenAlex ends up with both terms.
- Report grouping: within an area, build `{term_name: [articles]}`. An article
  with multiple terms appears under each of its terms (simplest, matches folder
  intuition). Score-sort within each group. Add a small per-article badge
  listing all its matched terms so cross-term overlap is visible.

## Implementation steps

1. `models.py` — add `matched_terms` field; extend `citation`/template context
   as needed.
2. `pipeline.py` — thread `term_name` from each per-term source call onto
   results; ensure enrichment preserves it.
3. `sources/dedupe.py` — union `matched_terms` and `sources` on merge; add a
   test for the union.
4. `report.py` / `templates/area.html.j2` — render grouped-by-term sections
   with headings; keep the score sort within groups; add the term badge and the
   borderline flag (subtask 08) hook.
5. `AreaIndexRow` — optionally show per-term counts on the index.

## Files touched
`models.py`, `pipeline.py`, `sources/dedupe.py`, `report.py`,
`templates/area.html.j2`, `templates/index.html.j2`; tests.

## Acceptance criteria
- An article matched by two terms lists both in `matched_terms` after dedupe
  (unit test).
- `data_science` report renders four term sections (only non-empty ones shown),
  each score-sorted.
- Report is stable/deterministic given the same retained set (golden HTML test
  or snapshot of the grouping structure).
