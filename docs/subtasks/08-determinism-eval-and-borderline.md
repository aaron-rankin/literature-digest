# Subtask 08 — Determinism eval command + borderline flag

**To-do:** Paper Processing → "how deterministic is the scoring … and sensitivity?"
**Decisions:** D9
**Depends on:** 07 (screenings table), 06 (test DB / fast model), 05 (report template)

## Goal

Quantify screening determinism offline, and surface threshold sensitivity to
report readers.

## Part A — `screen-eval` command

- New CLI subcommand: `literature-digest screen-eval --area <slug> [--k 5]
  [--sample N] [--fast]`.
- Takes a fixed sample of articles (from the last run's `screenings`, or a small
  frozen fixture set for reproducibility), re-screens each **K** times, and
  reports per-article and aggregate:
  - score mean / std-dev / min / max;
  - **category-flip rate** (fraction of articles whose category changed across
    the K runs);
  - **threshold-flip rate** (fraction crossing the area threshold across runs).
- Writes to the **test DB** (never prod), tags rows with the model, and prints a
  `rich` summary table.
- This is the tool that answers "how deterministic is it, and how sensitive to
  the cutoff" for a given model.

## Part B — borderline flag in reports

- Add `settings.borderline_band` (default e.g. `5`).
- An article is **borderline** if `abs(score - threshold) <= borderline_band`.
- `report.py` marks borderline retained articles with a visible tag; optionally
  list borderline *dropped* articles (just below cutoff) in a collapsed
  "borderline — just missed" section so near-misses aren't invisible.

## Implementation steps

1. `cli.py` — add `screen-eval` subcommand + args; `cmd_screen_eval`.
2. New `src/literature_digest/eval.py` — sampling, K-repeat screening, stats.
3. `config.py` — add `borderline_band`.
4. `report.py` / `templates/area.html.j2` — borderline tag + optional near-miss
   section (uses the retained/dropped split from the run).

## Files touched
`cli.py`, `eval.py` (new), `config.py`, `report.py`, `templates/area.html.j2`;
tests.

## Acceptance criteria
- `screen-eval --area data_science --k 5` prints std-dev + flip rates and writes
  only to the test DB.
- With a mocked deterministic LLM, flip rate reports 0; with a mocked jittery
  LLM, it reports > 0 (unit test).
- Reports visibly flag articles within ±`borderline_band` of the threshold.
