# Issue: OpenAlex/Crossref 429 Too Many Requests on first run

## Status
Open

## Summary
Running the pipeline for the first time against `data_science` immediately hits a `429 Too Many Requests` response from OpenAlex. Crossref also appears slow/unresponsive. The current `_safe_fetch` wrapper catches the error and skips the source, which means the pipeline completes but ingests nothing.

## Environment
- OS: macOS (Apple Silicon)
- Python: 3.11.15 via `uv`
- Command: `uv run literature-digest run --area data_science --limit 5`
- Contact email supplied via `.env` (polite pool `mailto=` is present in URLs)

## Steps to reproduce
1. Ensure `.env` has `CONTACT_EMAIL` set.
2. Run `uv run literature-digest run --area data_science --limit 5`.
3. Observe OpenAlex returns 429 on the first request:

```text
#data_science since=first run
  openalex unavailable: HTTPStatusError("Client error '429 Too Many Requests' for url
'https://api.openalex.org/works?search=%22game+model%22+OR+%22football%22+OR+%22soccer%22
&per-page=100&cursor=%2A&mailto=...'") — skipping
```

## Expected behavior
The pipeline should tolerate free-API rate limits by backing off and retrying, rather than skipping the source entirely on the first 429.

## Actual behavior
- OpenAlex is skipped after the first 429.
- Crossref is then called and appears to hang or also rate-limit.
- No articles are ingested.

## Root-cause hypotheses
1. **No retry/backoff.** `_safe_fetch` only catches `httpx.HTTPError` and returns `[]`; it never retries transient 429s.
2. **No request spacing.** Each term query is issued immediately after the previous one, which can trigger per-second rate limits even when each query is small.
3. **No `Retry-After` handling.** The 429 response likely includes a `Retry-After` header that we ignore.
4. **Crossref is also un-throttled.** The same no-backoff logic applies to Crossref.

## Proposed fixes
1. Add a small shared `httpx.Client` with retry transport (or custom retry loop) for 429 / 503 / 504.
2. Implement exponential backoff with jitter, capping total wait time.
3. Respect `Retry-After` header when present.
4. Add a short fixed delay (e.g. 0.5–1 s) between successive term queries within one source.
5. Consider a local response cache for the current run so repeated identical queries are not re-issued.

## Acceptance criteria
- `literature-digest run --area data_science --limit 5` eventually succeeds or fails with a clear error after retries are exhausted.
- 429 responses are retried at least 3 times with backoff.
- Unit tests mock 429 → 200 transitions and verify retry behavior.
- No source is silently skipped solely because of a transient 429.
