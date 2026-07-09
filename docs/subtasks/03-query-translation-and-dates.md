# Subtask 03 — Query translation + date injection

**To-do:** Paper Finding → cross-source discovery
**Decisions:** D2, D4
**Depends on:** 02 (parser), 01 (loader provides terms)

## Goal

Turn each `ParsedQuery` into the query params each source needs, and inject the
pipeline-owned crawl window (indexed/created date) uniformly, while translating
`PUBYEAR` to each source's publication-date filter.

## Two date axes (keep them separate — this is the crux)

| Axis | Source of truth | Scopus | OpenAlex | Crossref |
|------|-----------------|--------|----------|----------|
| **Crawl window** (incremental "new since last run") | pipeline `last_run` − overlap → now | `ORIG-LOAD-DATE AFT/BEF <epoch>` (re-injected) | `from_created_date` (filter) | `from-index-date` |
| **Publication recency** (`PUBYEAR`) | authored in `.txt` | `PUBYEAR > / <` (kept) | `from_publication_date` / `to_publication_date` | `from-pub-date` / `until-pub-date` |

> **Bug to fix in passing:** `openalex.py` currently puts the crawl `since` into
> `from_publication_date`, conflating the two axes. After this subtask the crawl
> window must use `from_created_date` and `PUBYEAR` must use
> `from_publication_date`.

## Translation rules (term tree → source query)

- **Scopus:** re-render the tree back to DSL (`TITLE-ABS-KEY(...) AND/OR ...`) and
  append the injected `ORIG-LOAD-DATE` window + preserved `PUBYEAR`. Effectively
  round-trips the authored query with a fresh date window.
- **OpenAlex:** boolean `search` string. OpenAlex `search` supports quoted
  phrases and `AND`/`OR`/parentheses to a degree — render the tree to that
  syntax; where nesting isn't supported, flatten to the dominant `AND` of
  `OR`-groups (document the approximation). Field distinction
  (`TITLE-ABS-KEY-AUTH` vs `TITLE-ABS-KEY`) collapses — both map to full-text
  `search`.
- **Crossref:** `query.bibliographic` free-text = space-joined content terms
  (Crossref has no real boolean); rely on `PUBYEAR` + index-date filters +
  downstream screening to prune. This is the crudest translation by design.

## Interface

```python
@dataclass
class SourceQuery:
    term_name: str          # for matched_terms tagging (subtask 05)
    parsed: ParsedQuery

class QueryTranslator:
    def to_scopus(self, q: SourceQuery, window: DateWindow) -> str
    def to_openalex(self, q: SourceQuery, window: DateWindow) -> dict
    def to_crossref(self, q: SourceQuery, window: DateWindow) -> dict
```

`DateWindow = {crawl_from, crawl_to, pub_from, pub_to}` computed once per area
run from `last_run`, `lookback_days`, and the query's `pubyear_from/to`.

## Implementation steps

1. New `src/literature_digest/query/translate.py`.
2. Source `search()` signatures change from `(area, since)` to
   `(source_query, window)` (or accept a list and loop). Update
   `openalex.py`, `crossref.py`, `scopus_api.py`.
3. `run_area` loops over the area's terms, builds a `DateWindow` per term,
   calls each source per term, and tags results (subtask 05).

## Files touched
`query/translate.py` (new), `sources/openalex.py`, `sources/crossref.py`,
`sources/scopus_api.py`, `pipeline.py`; tests.

## Acceptance criteria
- OpenAlex crawl window uses `from_created_date`, not `from_publication_date`.
- `PUBYEAR 2024–2026` from a `.txt` shows up as `from/to_publication_date` on
  OpenAlex and `from/until-pub-date` on Crossref.
- Scopus round-trip test: parse → translate → DSL preserves boolean structure
  and injects the current crawl window.
- Golden test per source for `game_model.txt` params.
