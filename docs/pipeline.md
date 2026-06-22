# Pipeline Diagram

Source of truth for the literature-digest pipeline flow. Phase 1 (skeleton)
is complete; the structure below stays stable as phases 2-5 fill in the
placeholder bodies.

```mermaid
flowchart TD
    accTitle: Literature Digest Pipeline Flow
    accDescr: Two-week cron triggers per-area ingestion from Scopus alert emails and free APIs; articles are deduped, LLM-screened against org context, summarized with action points, and rendered to per-area HTML plus an index.

    trigger["⏰ Cron / launchd<br/>every 2 weeks"]
    load["📚 Load config<br/>areas.yaml + org_context.md"]
    outer{"🔄 For each<br/>research area"}
    fork["📥 Fetch in parallel"]
    fetch_email["📬 IMAP fetch<br/>Scopus alert emails"]
    fetch_api["🌐 Poll OpenAlex +<br/>Crossref + Semantic Scholar"]
    parse["🔍 Parse emails<br/>extract DOIs"]
    enrich["🔬 Scopus API enrich<br/>metadata + abstract"]
    dedupe["🧬 Dedupe & merge<br/>by normalized DOI"]
    inner{"🔁 For each<br/>article"}
    screen["🤖 LLM screen<br/>relevancy score 0-100"]
    threshold{"✅ Score ≥ 60"}
    drop["🗑️ Drop article"]
    summarize["📝 LLM summarize<br/>1-3 action points"]
    render_area["🎨 Render area HTML<br/>+ update index"]
    state["💾 Update SQLite +<br/>move emails to Processed"]
    done["📂 Open index.html"]

    trigger --> load --> outer
    outer -- yes --> fork
    fork --> fetch_email --> parse
    fork --> fetch_api --> enrich
    parse --> enrich --> dedupe --> inner
    inner -- yes --> screen --> threshold
    threshold -- no --> drop --> inner
    threshold -- yes --> summarize --> inner
    inner -- no --> render_area --> state
    state --> outer
    outer -- no --> done

    classDef trigger fill:#fef9c3,stroke:#ca8a04,color:#713f12,stroke-width:2px
    classDef io fill:#dbeafe,stroke:#2563eb,color:#1e3a5f
    classDef llm fill:#fae8ff,stroke:#a21caf,color:#701a75,stroke-width:2px
    classDef store fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef decision fill:#ffedd5,stroke:#ea580c,color:#7c2d12
    classDef terminal fill:#fee2e2,stroke:#dc2626,color:#7f1d1f,stroke-width:2px

    class trigger trigger
    class load,fetch_email,fetch_api,parse,enrich,dedupe,render_area,done io
    class screen,summarize llm
    class state store
    class outer,inner,threshold decision
    class drop terminal
```

## Stage mapping to modules

| Stage | Module | Phase |
| ----- | ------ | :---: |
| Load config | `config.py` | 1 ✅ |
| IMAP fetch | `sources/scopus_email.py` | 3 |
| Parse + extract DOIs | `sources/scopus_email.py` | 3 |
| Scopus API enrich | `sources/scopus_api.py` | 3 |
| Poll free APIs | `sources/openalex.py`, `sources/crossref.py` | 2 |
| Dedupe & merge | `sources/dedupe.py` | 2 |
| LLM screen | `screen.py` | 4 |
| LLM summarize | `summarize.py` | 4 |
| Render HTML | `report.py` | 1 ✅ |
| Update state | `store.py` | 1 ✅ |
| Orchestration | `pipeline.py` | 1 ✅ |
| Schedule | `scripts/launchd.plist.tmpl` | 5 |
