# Subtask 04 — Real Scopus API source

**To-do:** Paper Finding → "link up Scopus API: key is in `.env`"
**Decisions:** D2, D3, D4
**Depends on:** 03 (query building), 02 (parser)

## Goal

Replace the `scopus_api.py` placeholder with a working Elsevier Scopus Search
API client for both `search()` (discovery by query) and `enrich()` (metadata by
DOI).

## Design

- Endpoint `https://api.elsevier.com/content/search/scopus`.
- Headers: `X-ELS-APIKey: {scopus_api_key}`, optional `X-ELS-Insttoken:
  {scopus_inst_token}`, `Accept: application/json`.
- `search(source_query, window)`:
  - `query` = `QueryTranslator.to_scopus(source_query, window)`.
  - Paginate via `start` / `count` (max 25/page on the standard view) using
    `opensearch:totalResults` + `link[@ref=next]`.
  - Parse each entry → `Article` (title, `dc:description` abstract if present,
    `dc:creator`/authors, `prism:publicationName`, year from
    `prism:coverDate`, DOI from `prism:doi`, `sources=["scopus"]`).
  - Abstracts are often absent from the search view → leave `abstract=None` and
    let OpenAlex/Crossref enrichment or the abstract-retrieval API fill it (note
    the quota cost; default to leaving None).
- `enrich(doi)`: `query=DOI(<doi>)`, return first entry as `Article` or `None`.
- **Backoff:** Scopus quotas are strict. On HTTP 429 or `X-RateLimit-Remaining:
  0`, exponential backoff with jitter, capped retries; on exhaustion raise
  `httpx.HTTPError` so `_safe_fetch` downgrades the source to empty (run
  continues on OpenAlex/Crossref).
- **Quota logging:** log `X-RateLimit-Remaining` / `-Reset` after each call so
  quota exhaustion is visible.

## Implementation steps

1. Implement `search` + `enrich` bodies in `sources/scopus_api.py` with an
   `httpx.Client`, following the `openalex.py` structure (cursor/pagination,
   `_parse_*`, `_get` with retry).
2. Add a shared retry/backoff helper (reuse for OpenAlex/Crossref in subtask 09).
3. Wire `test-scopus` CLI sanity command (mirror `test-llm`): one cheap query,
   print count + remaining quota.

## Files touched
`sources/scopus_api.py`, `cli.py`, tests (with recorded/mocked responses).

## Acceptance criteria
- `literature-digest test-scopus` returns results against a real key.
- 429 triggers backoff then graceful empty-result downgrade (unit test with a
  mocked 429-then-200).
- Enrichment loop in `pipeline.py` (email stubs / DOI-only) resolves via Scopus
  first, OpenAlex fallback (existing behavior preserved).
- Results carry `sources=["scopus"]` and dedupe correctly against OpenAlex/
  Crossref hits for the same DOI.
