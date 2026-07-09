# Subtask 10 — Containerisation (deferred)

**To-do:** Pipeline → "containerising the whole thing"
**Decisions:** D10 (deferred until logic stable), D11 (disk-only delivery)
**Depends on:** 09 (stable, hardened pipeline)

## Goal

Package the pipeline as a **run-once** container image, triggered by an external
scheduler on the ~2-week cadence. Do this **last**, after 01–09 stabilise, to
avoid rebuilding images through logic churn.

## Design (to confirm when we get here)

- **Run-once, exits.** Container runs `literature-digest run` and exits (not a
  long-lived service). Matches the batch nature of a bi-weekly digest.
- **State + secrets via volumes.** Mount `data/` (holds `state.db` + reports)
  and pass `.env` / secrets in; the image stays stateless.
- **Scheduling.** External trigger — keep the existing `launchd` on the Mac, or
  a host `cron`, or a CI cron (GitHub Actions) invoking the image. (Deferred
  decision: which host actually runs it in production.)
- Base image: slim Python matching `pyproject.toml`; install via `uv`.
- No headless-browser deps needed (PDF was declined, D7).

## Implementation steps (later)

1. `Dockerfile` (multi-stage: build wheels with `uv`, slim runtime).
2. `.dockerignore` (exclude `.venv`, `data/`, caches).
3. Document `docker run` with volume mounts + env file.
4. Convert `scripts/launchd.plist.tmpl` to invoke the container (or keep native
   and containerise only for portability).

## Open decisions to revisit before starting
- Where does the container actually run (Mac launchd vs a small always-on host
  vs CI cron)?
- Is delivery still disk-only (D11), or do we add email/publish first so a
  scheduled container's output actually reaches readers?

## Acceptance criteria (later)
- `docker run --env-file .env -v $PWD/data:/app/data <image> run` produces the
  same reports as a local run.
- Image is stateless; deleting/recreating the container loses no state.
