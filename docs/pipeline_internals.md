# Pipeline Internals — Scripts & Functions

A code-level view of the heavy lifting in `src/literature_digest/`. Each node is the
real function or method that does the work, with its source location. For the
conceptual flow (cron → ingest → screen → render), see
[Pipeline Diagram](pipeline.md).

```mermaid
flowchart TB
    accTitle: Literature Digest Call Graph
    accDescr: Code-level flow from the CLI entrypoint through pipeline.run_area and run_all, showing the actual functions in sources, screen, summarize, store, and report that perform ingestion, dedupe, LLM screening, summarizing, and HTML rendering.

    entry(["💻 cli.main<br/>cli.py:97"]) --> parse_args["⚙️ build_parser<br/>cli.py:70"]
    parse_args --> cmd_run["🏃 cmd_run<br/>cli.py:48"]
    cmd_run --> run_all

    subgraph orchestrator ["🧭 pipeline.py"]
        run_all["🔁 run_all<br/>pipeline.py:101"]
        load_areas["📚 config.load_areas<br/>config.py:78"]
        load_ctx["📄 config.load_org_context<br/>config.py:85"]
        run_area["🔄 run_area<br/>pipeline.py:32"]
        run_all --> load_areas
        run_all --> load_ctx
        run_all --> run_area
    end

    subgraph sources ["📡 sources/"]
        fetch_email["📬 ScopusEmailSource.fetch_articles<br/>scopus_email.py"]
        search_api["🌐 ScopusApiSource.search<br/>scopus_api.py"]
        search_oa["🌐 OpenAlexSource.search<br/>openalex.py"]
        search_cr["🌐 CrossrefSource.search<br/>crossref.py"]
        enrich_api["🔬 ScopusApiSource.enrich<br/>scopus_api.py"]
        enrich_oa["🔬 OpenAlexSource.enrich<br/>openalex.py"]
        dedupe["🧬 Deduper.dedupe<br/>dedupe.py:31"]
    end

    subgraph llm ["🤖 screen.py + summarize.py"]
        screen["📏 Screener.screen<br/>screen.py:77"]
        summarize["📝 Summarizer.summarize<br/>summarize.py:44"]
        complete_json["⚙️ LLMClient.complete_json<br/>screen.py:58"]
        screen --> complete_json
        summarize --> complete_json
    end

    subgraph store ["💾 store.py"]
        get_last["/get_last_run<br/>store.py:76"]
        start_run["start_run<br/>store.py:93"]
        is_seen["is_seen<br/>store.py:61"]
        mark_seen["mark_seen<br/>store.py:68"]
        finish_run["finish_run<br/>store.py:101"]
        set_last["set_last_run<br/>store.py:83"]
    end

    subgraph report ["🎨 report.py"]
        render_area[" render_area<br/>report.py:52"]
        render_index["render_index<br/>report.py:44"]
    end

    run_area --> get_last
    run_area --> start_run
    run_area --> fetch_email
    run_area --> search_api
    run_area --> search_oa
    run_area --> search_cr
    fetch_email -.->|"stub.doi"| enrich_api
    fetch_email -.->|"fallback"| enrich_oa
    enrich_api --> dedupe
    enrich_oa --> dedupe
    search_api --> dedupe
    search_oa --> dedupe
    search_cr --> dedupe
    dedupe --> is_seen
    is_seen -->|new| screen
    screen -->|score ≥ threshold| summarize
    screen -->|below| mark_seen
    summarize --> mark_seen
    mark_seen --> is_seen
    is_seen -->|done| finish_run
    finish_run --> set_last
    run_area --> render_area
    run_all --> render_index
    render_index --> done(["📂 index.html written"])

    classDef entry_style fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#3b0764
    classDef orch_style fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a5f
    classDef src_style fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e
    classDef llm_style fill:#fae8ff,stroke:#a21caf,stroke-width:2px,color:#701a75
    classDef store_style fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef report_style fill:#fef9c3,stroke:#ca8a04,color:#713f12
    classDef terminal_style fill:#fee2e2,stroke:#dc2626,stroke-width:2px,color:#7f1d1f

    class entry,parse_args,cmd_run entry_style
    class run_all,load_areas,load_ctx,run_area orch_style
    class fetch_email,search_api,search_oa,search_cr,enrich_api,enrich_oa,dedupe src_style
    class screen,summarize,complete_json llm_style
    class get_last,start_run,is_seen,mark_seen,finish_run,set_last store_style
    class render_area,render_index,done report_style
```

## Where the heavy lifting lives

| Stage | Function | File:Line | What it does |
| ----- | -------- | --------- | ------------ |
| Entrypoint | `cli.main` | `cli.py:97` | Parse args, dispatch subcommand |
| Orchestration | `pipeline.run_all` | `pipeline.py:101` | Load config, build clients, loop areas, render index |
| Per-area | `pipeline.run_area` | `pipeline.py:32` | Fetch → enrich → dedupe → screen → summarize → persist |
| Email ingest | `ScopusEmailSource.fetch_articles` | `sources/scopus_email.py` | IMAP pull of Scopus alert emails |
| API ingest | `ScopusApiSource.search` / `.enrich` | `sources/scopus_api.py` | Scopus query + DOI enrichment |
| Free-API ingest | `OpenAlexSource.search` / `.enrich` | `sources/openalex.py` | OpenAlex query + DOI enrichment |
| Free-API ingest | `CrossrefSource.search` | `sources/crossref.py` | Crossref query |
| Merge | `Deduper.dedupe` | `sources/dedupe.py:31` | Normalize DOIs, merge by precedence |
| Screening | `Screener.screen` | `screen.py:77` | LLM relevancy score 0-100 + category |
| Summary | `Summarizer.summarize` | `summarize.py:44` | LLM action-point extraction (1-3) |
| LLM call | `LLMClient.complete_json` | `screen.py:58` | Single LiteLLM call, JSON-validated |
| State | `Store.*` | `store.py:61`-`109` | seen-DOI filter, run log, last-run cursor |
| Render | `ReportRenderer.render_area` / `.render_index` | `report.py:44`-`76` | Jinja2 → per-area + index HTML |

> Note: ingestion and LLM functions are currently placeholder bodies (Phases 2-4).
> The orchestrator shape and the render/state modules are stable from Phase 1.