# CLAUDE.md

Guidance for agents working in this repository.

## Always use the `uv` environment — never the system interpreter

This project is managed with [`uv`](https://docs.astral.sh/uv/). **Every** Python
command, script, tool, or test run **must** go through `uv` so it uses the
project's locked virtual environment (`uv.lock` / `.venv`). Do **not** call a
bare `python`/`pip`/`pytest`/`ruff`, and do **not** manually `source
.venv/bin/activate`.

Run commands with `uv run …` (it resolves and syncs the env automatically):

| Task | Command |
|------|---------|
| Run the pipeline | `uv run literature-digest run` |
| Run one area / dry run | `uv run literature-digest run --area data_science --limit 5` |
| List areas | `uv run literature-digest list-areas` |
| LLM sanity check | `uv run literature-digest test-llm` |
| Tests | `uv run pytest` |
| Tests + coverage | `uv run pytest --cov` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Add a runtime dependency | `uv add <pkg>` |
| Add a dev dependency | `uv add --dev <pkg>` |
| Sync env from lockfile | `uv sync` |

Rules of thumb:
- Prefix any Python invocation with `uv run`.
- Manage dependencies with `uv add` / `uv remove` (which update `pyproject.toml`
  and `uv.lock`) — never `pip install`.
- If a command fails because a package is missing, `uv sync` first; do not fall
  back to the system Python.

## Implementing a task — always on a new branch

When you start work on a new task or subtask (e.g. one of `docs/subtasks/`), do
**not** commit to the default branch. Each task gets its own branch:

1. Start from an up-to-date default branch:
   `git switch main && git pull` (this repo's mainline; `master` locally).
2. Create a task branch named for the work, e.g.
   `git switch -c subtask-02-scopus-parser` (pattern:
   `subtask-<NN>-<short-slug>`; for non-subtask work use a descriptive slug).
3. Do the work on that branch — **one task per branch**. Keep it focused; don't
   fold unrelated changes in.
4. Commit in logical steps with clear messages. Run `uv run pytest` and
   `uv run ruff check .` before committing.
5. Open a PR against the default branch when the task is complete; don't merge
   your own work into mainline without review unless the user asks.

Only commit or push when the user asks. If you're ever on the default branch
with changes to make, branch first.

## Project shape

- Package: `src/literature_digest/` — pipeline stages are
  `sources/ → dedupe → screen → summarize → report`, orchestrated by
  `pipeline.py`, exposed via `cli.py` (`literature-digest`).
- Config: `config/areas.yaml` (+ `config/organisation_context.md`), env via `.env`.
- Search queries: `data/search_terms/<area>/<term>.txt`.
- Plans: `docs/subtasks/` (see `docs/subtasks/README.md` for the current roadmap
  and decision log).
