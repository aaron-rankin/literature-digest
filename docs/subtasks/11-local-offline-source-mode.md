# Subtask 11 — Fully-local offline source mode (fixtures)

**To-do:** new (debugging / cost control)
**Decisions:** D8 (test DB / fast model) — composes with this
**Depends on:** 05 (matched_terms on Article), pairs with 06 (`--fast` local LLM)

## Goal

Run the whole pipeline against a fixed set of local papers — **no Scopus /
OpenAlex / Crossref calls** — so screening, summarization, and reporting can be
iterated on without burning API quota, and without waiting on flaky networks.
Combined with a local Ollama model (`--fast`), this is a **zero-external-API**
run.

## Why not just drop files in `data/test/sources`?

Same idea, cleaner shape:
- Location `data/fixtures/<area>/*.json` — distinct from `state.test.db`
  (subtask 06) and the pytest `tests/fixtures/`; grouped by area so each paper
  maps to the right report.
- Fixtures are **normalized `Article` JSON** (the pain is downstream of parsing:
  API limits + the slow LLM loop). Raw-response parsing stays covered by unit
  tests in subtasks 02–04.

## Design

### Fixture format
One JSON file per paper (or a list per file), matching the `Article` model:
```json
{
  "doi": "10.1234/abcd",
  "title": "...",
  "abstract": "...",
  "authors": ["Smith, J.", "Doe, A."],
  "journal": "J. Sports Sci.",
  "year": 2025,
  "sources": ["fixture"],
  "area_slug": "data_science",
  "matched_terms": ["game_model"]
}
```
`area_slug` + `matched_terms` are read straight from the fixture; if
`matched_terms` is absent, default to the area's term names.

### `LocalSource` (`sources/local.py`)
- Implements the same interface as the other sources
  (`search(source_query, window) -> list[Article]`).
- Ignores the query/date window; loads every `*.json` under
  `data/fixtures/<area.slug>/`, validates against `Article`, tags
  `sources=["fixture"]`.
- Returns them so they flow through dedupe → screen → summarize → render
  unchanged.

### `--local` run mode (`cli.py` / `pipeline.py`)
- `literature-digest run --local [--area <slug>] [--fast]`.
- When set, `run_all` builds **only** `LocalSource` (network sources are not
  constructed/called).
- **Disable seen-skipping and never advance `last_run`** so the same fixtures
  re-process on every run (this is the debug loop). Route to a dedicated
  `data/state.local.db` (or `:memory:`) so prod `seen_dois`/`last_run` are
  untouched — reuses the separate-DB pattern from subtask 06.
- `--fast` selects the local Ollama model → `--local --fast` = no external APIs
  at all.

### `--capture` (build fixtures from one real run)
- `literature-digest run --area data_science --limit 5 --capture`.
- Runs the normal (networked) fetch + dedupe, then writes the resulting
  `Article`s (pre-screen) to `data/fixtures/<area>/<doi-or-slug>.json` and
  **exits before screening** (or continues, per flag). Gives a realistic fixture
  set from a single quota-cheap run; iterate offline afterward.

## Implementation steps
1. `sources/local.py` — `LocalSource` + fixture loader/validator.
2. `sources/__init__.py` — export `LocalSource`.
3. `config.py` — add `fixtures_dir: Path = Path("./data/fixtures")`.
4. `pipeline.py` — `run_all(..., local=False, capture=False)`: branch source
   construction; disable seen-skip + last_run advance in local mode; pick
   `state.local.db`.
5. `cli.py` — add `--local` and `--capture` to `run`.
6. `.gitignore` — ignore `data/fixtures/*` contents but keep a `.gitkeep`;
   optionally commit a tiny 2–3 paper example set for smoke tests.
7. Docs — README + `AGENTS.md` note the offline loop.

## Files touched
`sources/local.py` (new), `sources/__init__.py`, `config.py`, `pipeline.py`,
`cli.py`, `.gitignore`, `README.md`; tests.

## Acceptance criteria
- `run --local --fast` makes **zero** network calls to Scopus/OpenAlex/Crossref
  (assert via mocked/blocked HTTP in a test) and renders reports from fixtures.
- Running `--local` twice reprocesses the same papers both times (seen-skip
  disabled; prod DB untouched).
- `run --area data_science --limit 3 --capture` writes valid `Article` JSON to
  `data/fixtures/data_science/` that a subsequent `--local` run replays.
- A committed 2–3 paper example fixture set drives an end-to-end smoke test with
  a stub LLM.
