# Subtask 07 — Persist screening scores

**To-do:** Paper Processing → "are previous outputs stored in db, or just HTML?"
**Decisions:** D6, D8
**Depends on:** 06 (DB path selection, model identity)

## Goal

Persist each screening result (not full articles) so scoring can be analyzed
over time, keeping fast-model and prod-model scores separable.

## Design

New table in `store.py`:

```sql
CREATE TABLE IF NOT EXISTS screenings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER NOT NULL,
    area_slug  TEXT NOT NULL,
    doi        TEXT,
    title      TEXT,          -- for readability when DOI is null
    model      TEXT NOT NULL, -- e.g. "ollama/llama3.2:1b" or "anthropic/claude-..."
    score      INTEGER NOT NULL,
    category   TEXT NOT NULL,
    rationale  TEXT,
    screened_at TEXT NOT NULL
);
```

- Written for **every** screened article (retained or dropped), so drop-rate and
  borderline analysis have full data.
- `model` is recorded explicitly even though fast runs also use a separate DB —
  belt to the test-DB braces, and future-proofs a prod model change.
- Reports still render from the in-flight retained list (not from this table);
  this table is for analysis + the `screen-eval` command (subtask 08).

## Implementation steps

1. `store.py` — add table to `SCHEMA` and a
   `record_screening(run_id, area_slug, article, model)` method.
2. `pipeline.py` — after `screener.screen(...)`, call
   `store.record_screening(...)` with the active model id (thread the model id
   from `run_all`).
3. Add a `screenings` read helper for subtask 08
   (`fetch_screenings(area_slug=None, model=None) -> list[...]`).

## Files touched
`store.py`, `pipeline.py`; tests.

## Acceptance criteria
- After a run, every screened article has one `screenings` row with the correct
  model id.
- Fast run rows live only in `state.test.db`; prod rows only in `state.db`.
- Schema migration is lazy/idempotent (existing DBs get the new table on next
  connect without data loss).
