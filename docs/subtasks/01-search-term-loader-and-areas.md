# Subtask 01 — Search-term loader + thin `areas.yaml`

**To-do:** Paper Finding → "link up new search terms: `/data/search_terms`"
**Decisions:** D1, D5
**Depends on:** nothing (foundation)

## Goal

Make `data/search_terms/<area>/<term>.txt` the source of truth for queries, and
reduce `areas.yaml` to thin per-area metadata keyed by folder slug.

## Design

- Auto-discover areas by listing directories under `settings.search_terms_dir`
  (default `data/search_terms/`).
- Each area's queries = the `*.txt` files in its folder; `term` name = filename
  stem (`game_model`, `tracking_data`, …).
- An area folder with **zero** `.txt` files is **skipped** (so empty
  `nutrition/` and `performance/` folders cause no runs yet).
- `areas.yaml` maps slug → `{name, threshold?, enabled?}`. A folder with no
  matching entry uses `name = title-cased slug`, `threshold = defaults`,
  `enabled = true`. `enabled: false` skips an area even if it has queries.

## Implementation steps

1. **`config.py`**
   - Add `search_terms_dir: Path = Path("./data/search_terms")` to `Settings`.
   - Repurpose `AreaConfig` to metadata only: `slug`, `name`,
     `threshold: int | None`, `enabled: bool = True`. Remove `keywords` and
     `scopus_query`.
   - Add a `SearchTerm` model: `{name: str, raw_query: str, path: Path}`.
   - New loader `discover_areas(settings) -> list[LoadedArea]` where
     `LoadedArea = {config: AreaConfig, terms: list[SearchTerm]}`:
     - list subdirs of `search_terms_dir`;
     - for each, read `*.txt` (skip empties);
     - merge with `areas.yaml` metadata (yaml optional / partial);
     - drop disabled + query-less areas.
   - Keep `AreasFile.threshold_for` / `lookback_days` semantics.
2. **`config/areas.yaml`** — rewrite:
   ```yaml
   defaults:
     threshold: 60
     lookback_days: 17
   areas:
     - slug: data_science
       name: Data Science
       threshold: 55
     # nutrition / performance added when they get .txt queries
   ```
   Remove `sports-nutrition` / `recovery-and-sleep`.
3. **`pipeline.py`** — `run_all` iterates `discover_areas()` instead of
   `areas_file.areas`; pass each area's `terms` down into `run_area`.
4. **`cli.py`** — `list-areas` shows term count per area instead of `keywords`.
5. **Cleanup** — delete stale committed reports
   `data/reports/areas/sports-nutrition.html`,
   `data/reports/areas/recovery-and-sleep.html`, and regenerate `index.html`.

## Files touched
`config.py`, `config/areas.yaml`, `pipeline.py`, `cli.py`,
`data/reports/areas/*` (delete stale).

## Acceptance criteria
- `literature-digest list-areas` lists `data_science` with 4 terms.
- Adding a `.txt` to a folder makes it appear next run with no code change.
- Empty `nutrition/` / `performance/` folders produce no run and no error.
- Unit test: `discover_areas` on a temp tree returns expected areas/terms and
  skips empty + disabled ones.
