# Tasks

## Paper Finding
[x] - link up new search terms: `/data/search_terms` (subtask 01 — merged to main)
[x] - link up Scopus API: key is in `.env` (subtasks 03–04 — in PR)

--- 

## Paper Processing
[x] - Add option for linking to OAI/ANTHROPIC keys (supported via LiteLLM env; documented in .env.example)
[x] - Add local model that is smaller so quicker processing on test runs (subtask 06 preview — `--fast` flag + `state.test.db`)
[x] - Is model context getting refreshed for each paper processed (yes — single-message completions at temperature=0)
[] - Report generation: format per section, content of output, structure of output, by search term, do we also want a pdf output too (subtask 05 + 12)
[] - are previous outputs stored in db, or just the outputted HTML (subtask 07 — screenings persistence)
[] - how deterministic is the scoring of the papers and sensitivity (subtask 08)

--- 
## Pipeline
[] - containerising the whole thing (subtask 10 — deferred)
[] - Making sure it is robust (subtask 09)
[x] - cleaning up repo — stale example areas/reports removed (subtasks 01/09)
[] - updating documentation and pipeline diagrams (subtask 09)
[] - learning each component

---
## New ideas
[] - overhaul report UI to make reports sleeker, more digestible, and more presentable (subtask 12)
[] - change `--limit` from area-wide to per-search-term so dry runs exercise every term (subtask 13)
