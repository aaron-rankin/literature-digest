# Subtask 09 — Robustness, repo cleanup, docs

**To-do:** Pipeline → "robust", "cleaning up repo", "updating documentation and
pipeline diagrams", "learning each component"
**Decisions:** D10 (container deferred), D11 (disk-only)
**Depends on:** 01–08 landed (this is the hardening pass)

## Goal

Harden the local run and bring docs back in sync with the new design before
containerising.

## Robustness

- Shared retry/backoff helper for all three sources (429 / transient 5xx /
  timeouts) — extract from subtask 04, apply to OpenAlex + Crossref.
- Parser: unsupported-syntax terms are skipped with a clear per-term warning and
  a run-summary count, never a hard crash of the area.
- LLM failures already skip per-article; add a run-summary count of screening /
  summarization failures so silent skips are visible.
- Config validation on startup: missing Scopus key → warn (Scopus downgraded,
  free APIs still run); missing LLM creds → fail fast with a clear message.
- Tests: parser (subtask 02), translator golden tests (03), dedupe merge (05),
  store migration (07), and an end-to-end `run --fast --limit 2` smoke test with
  mocked sources + a stub LLM.

## Repo cleanup

- Remove the now-unused `keywords` / `scopus_query` remnants and any dead
  placeholder paths (`scopus_email` stays a stub per commit `ceb7853`, but mark
  it clearly).
- Delete stale committed reports; ensure `data/state*.db` and generated reports
  are `.gitignore`d appropriately (keep `.gitkeep`s).
- Reconcile `test-imap` (still placeholder) — either implement a minimal check
  or remove the command to avoid confusion.
- Ensure `data/search_terms/{nutrition,performance}/` keep a `.gitkeep` so empty
  areas survive checkout.

## Docs / diagrams

- Update `docs/pipeline.md` + `docs/pipeline_internals.md`: folder-as-source-of-
  truth, three-source translation, two date axes, per-term reporting, model
  tiering + test DB, screenings table, determinism eval.
- Refresh the pipeline diagram to show per-term fan-out → translate → 3 sources
  → dedupe(merge terms) → screen(persist) → summarize → group-by-term render.
- `README.md`: new CLI surface (`run --fast`, `screen-eval`, `test-scopus`),
  provider env profiles, how to add an area/term (drop a `.txt`).
- "Learning each component": add a short per-module one-liner map to
  `docs/pipeline_internals.md` (loader, parser, translator, sources, dedupe,
  screen, summarize, store, report).

## Acceptance criteria
- `uv run pytest` green, including the new smoke test.
- Fresh checkout + `.env` → `run --fast --limit 2` completes with a readable
  run summary (fetched / deduped / retained / dropped / failures / skipped-terms).
- Docs + diagram match the shipped behavior.
