# Subtask 06 — `--fast` test model + separate test DB

**To-do:** Paper Processing → "linking OAI/ANTHROPIC keys" + "smaller local model
for quicker test runs"
**Decisions:** D8
**Depends on:** nothing (parallel track); pairs with 07

## Goal

Keep one model for both stages in normal runs, add a `--fast` override that uses
a small local model for test runs, and route fast/test-run data to a **separate
DB file** so test scores never mix with prod scores.

## Design

- Config (`Settings`): keep `lit_model` / `lit_api_key` / `lit_api_base` as the
  default (prod) model. Add `lit_fast_model` (default e.g.
  `ollama/llama3.2:1b` or similar small local model) + optional
  `lit_fast_api_base`.
- `--fast` on `run` (and `screen-eval`, subtask 08):
  1. `LLMClient` uses the fast model for **both** screening and summarization;
  2. the state DB path switches from `data/state.db` to `data/state.test.db`.
- DB selection lives in one place: `run_all` picks
  `settings.data_dir / ("state.test.db" if fast else "state.db")`. Prod DB is
  never touched by a fast run.
- Consequence (accepted): fast runs don't share `seen_dois` / `last_run` with
  prod, so they re-fetch — fine for testing.
- **Provider switching is already supported** by LiteLLM via `lit_model` +
  `lit_api_key` + `lit_api_base` (OpenAI / Anthropic / Ollama). This subtask
  only documents it (README + `.env.example`): e.g. `LIT_MODEL=anthropic/
  claude-...`, `LIT_MODEL=openai/gpt-4o-mini`, `LIT_MODEL=ollama/llama3.1`.

## Implementation steps

1. `config.py` — add `lit_fast_model`, `lit_fast_api_base`.
2. `screen.py` `LLMClient` — accept an explicit model/base so `run_all` can
   construct it for fast vs prod (rather than always reading `settings.lit_model`).
3. `pipeline.py` `run_all(..., fast: bool = False)` — choose DB path + model.
4. `cli.py` — add `--fast` to `run`.
5. `.env.example` + `README.md` — document provider profiles and `--fast`.

## Files touched
`config.py`, `screen.py`, `pipeline.py`, `cli.py`, `.env.example`, `README.md`.

## Acceptance criteria
- `literature-digest run --fast` writes only to `data/state.test.db`; prod
  `state.db` mtime unchanged (test).
- `test-llm` reports which model (`--fast` vs default) it used.
- README documents switching to OpenAI/Anthropic/Ollama via env with no code
  change.
