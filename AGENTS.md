# AGENTS.md

Canonical agent guidance for this repo lives in [`CLAUDE.md`](./CLAUDE.md). The
most important rule is repeated here so this file is self-sufficient.

## Always use the `uv` environment — never the system interpreter

This project is managed with [`uv`](https://docs.astral.sh/uv/). **Every** Python
command, script, tool, or test run **must** go through `uv` so it uses the
project's locked virtual environment (`uv.lock` / `.venv`). Do **not** call a
bare `python`/`pip`/`pytest`/`ruff`, and do **not** manually `source
.venv/bin/activate`.

Use `uv run …`:

| Task | Command |
|------|---------|
| Run the pipeline | `uv run literature-digest run` |
| Run one area / dry run | `uv run literature-digest run --area data_science --limit 5` |
| List areas | `uv run literature-digest list-areas` |
| LLM sanity check | `uv run literature-digest test-llm` |
| Tests | `uv run pytest` |
| Lint / format | `uv run ruff check .` / `uv run ruff format .` |
| Add a dependency | `uv add <pkg>` (dev: `uv add --dev <pkg>`) |
| Sync env from lockfile | `uv sync` |

- Prefix any Python invocation with `uv run`.
- Manage dependencies with `uv add` / `uv remove` — never `pip install`.
- If a command fails because a package is missing, `uv sync` first; never fall
  back to the system Python.

## Implementing a task — always on a new branch

When you start a new task or subtask (e.g. one of `docs/subtasks/`), never
commit to the default branch. Each task gets its own branch:

1. Start from an up-to-date default branch: `git switch main && git pull`
   (mainline; `master` locally).
2. Create a task branch: `git switch -c subtask-<NN>-<short-slug>` (e.g.
   `subtask-02-scopus-parser`); use a descriptive slug for non-subtask work.
3. One task per branch — keep it focused, no unrelated changes.
4. Commit in logical steps with clear messages; run `uv run pytest` and
   `uv run ruff check .` before committing.
5. Open a PR against the default branch when done; don't merge into mainline
   without review unless the user asks.

Only commit or push when the user asks. If you're on the default branch with
changes to make, branch first.

## Logging — make it obvious where the pipeline gets stuck

The pipeline does slow, blocking work (per-source network fetches, per-article
LLM calls) where a hang or rate-limit is otherwise invisible. When implementing
or debugging, **write logs so the last-attempted step is always on screen:**

- **Log *before* each blocking call, not after** — print the stage + the item
  being processed (area slug, source name, DOI/title, "screening…"/"summarizing…")
  *before* the network/LLM call, so if it hangs the log shows exactly what it was
  waiting on.
- **Run with `--debug`**, which emits per-article screening/summarization
  progress (`cli.py`). Prefer extending this path over adding ad-hoc prints.
- **Timestamp long steps** so a stall is visible as a gap (e.g. log elapsed
  seconds per source fetch and per LLM call). Flag anything that exceeds a sane
  timeout.
- **Tee output to a log file** for long runs so it can be inspected after:
  `uv run literature-digest run --debug 2>&1 | tee data/logs/run-$(date +%F-%H%M).log`.
  Stdout is already line-buffered (`cli.py`), so logs stream in real time.
- Keep the run-summary counts (fetched / deduped / unseen / retained / dropped)
  and add failure/skip counts, so a run that "finished" but silently dropped
  everything is distinguishable from one that got stuck.

When a new component does slow or fallible work, add this logging as part of the
task — don't leave a blocking call unlogged.

See `CLAUDE.md` for the project shape and `docs/subtasks/README.md` for the
current roadmap.
