"""Pipeline orchestrator: wires sources -> dedupe -> screen -> summarize -> render.

Each stage currently calls into placeholder modules that return empty/neutral
results, so `run_all()` can be exercised end-to-end from the CLI. Phase-by-
phase we replace each placeholder with its real implementation without
changing the orchestrator's shape.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
from rich.console import Console

from literature_digest.config import (
    LoadedArea,
    Settings,
    discover_areas,
    load_areas,
    load_org_context,
)
from literature_digest.models import Article
from literature_digest.report import AreaIndexRow, ReportRenderer
from literature_digest.screen import LLMClient, Screener
from literature_digest.sources import (
    CrossrefSource,
    Deduper,
    OpenAlexSource,
    ScopusApiSource,
    ScopusEmailSource,
)
from literature_digest.store import Store
from literature_digest.summarize import Summarizer

console = Console()


def _safe_fetch(label: str, fn: Callable[[], list[Article]]) -> list[Article]:
    """Run one source fetch, downgrading network failures to an empty result.

    A single free API rate-limiting (HTTP 429) or being briefly unavailable must
    not abort the whole area run — we log it and let the other sources proceed.
    """
    try:
        return fn()
    except httpx.HTTPError as exc:
        console.print(f"[yellow]  {label} unavailable: {exc!r} — skipping[/]")
        return []


def run_area(
    area: LoadedArea,
    settings: Settings,
    store: Store,
    threshold: int,
    org_context: str,
    screener: Screener,
    summarizer: Summarizer,
    email_source: ScopusEmailSource,
    scopus_api: ScopusApiSource,
    openalex: OpenAlexSource,
    crossref: CrossrefSource,
    deduper: Deduper,
    limit: int | None = None,
    debug: bool = False,
) -> list[Article]:
    """Run the full pipeline for a single area. Returns retained articles.

    `limit` caps how many new articles are screened/summarized this run — for
    dry-running against a local LLM without waiting hours. A truncated run
    does NOT advance `last_run`, so the remaining articles are picked back up
    (and already-processed ones skipped via `seen_dois`) on the next run
    instead of falling outside the date-filter window forever.
    """
    last_run = store.get_last_run(area.slug)
    run_id = store.start_run(area.slug)
    console.print(f"[bold blue]#{area.slug}[/] since={last_run or 'first run'}")

    # ── 1. Fetch from all sources ──────────────────────────────────────────
    from_email = _safe_fetch("scopus_email", lambda: email_source.fetch_articles(area, last_run))
    from_scopus = _safe_fetch("scopus_api", lambda: scopus_api.search(area, last_run))
    from_openalex = _safe_fetch("openalex", lambda: openalex.search(area, last_run))
    from_crossref = _safe_fetch("crossref", lambda: crossref.search(area, last_run))
    console.print(
        "  fetched: "
        f"email={len(from_email)} scopus={len(from_scopus)} "
        f"openalex={len(from_openalex)} crossref={len(from_crossref)}"
    )

    # Enrich email-extracted DOIs via Scopus API + OpenAlex (Phase 3)
    enriched: list[Article] = []
    for stub in from_email:
        if stub.doi:
            art = scopus_api.enrich(stub.doi) or openalex.enrich(stub.doi) or stub
            enriched.append(art)
        else:
            enriched.append(stub)

    # ── 2. Dedupe & merge ──────────────────────────────────────────────────
    all_articles = enriched + from_scopus + from_openalex + from_crossref
    merged = deduper.dedupe(all_articles)
    for a in merged:
        a.area_slug = area.slug
    console.print(f"  deduped: {len(all_articles)} -> {len(merged)}")

    # ── 3. Filter already-seen ─────────────────────────────────────────────
    new_articles = [a for a in merged if not (a.doi and store.is_seen(a.doi, area.slug))]
    console.print(f"  unseen: {len(new_articles)}")

    truncated = False
    if limit is not None and len(new_articles) > limit:
        console.print(
            f"  [yellow]--limit {limit}: screening first {limit} of "
            f"{len(new_articles)} unseen articles; last_run will not advance[/]"
        )
        new_articles = new_articles[:limit]
        truncated = True

    # ── 4. Screen + 5. Summarize ───────────────────────────────────────────
    retained: list[Article] = []
    for art in new_articles:
        label = art.doi or art.title or "<untitled>"
        try:
            art.screening = screener.screen(art, area, org_context)
        except Exception as exc:  # one bad LLM response must not abort the run
            console.print(f"[yellow]  screening failed for {label!r}: {exc!r} — skipping[/]")
            continue
        if debug:
            console.print(
                f"  [screen] {label[:80]!r} score={art.screening.score} "
                f"category={art.screening.category!r}"
            )
        if art.screening.score >= threshold:
            try:
                art.action_points = summarizer.summarize(art, org_context)
            except Exception as exc:
                console.print(f"[yellow]  summarization failed for {label!r}: {exc!r}[/]")
            if debug:
                n = len(art.action_points)
                console.print(f"  [summarize] {label[:80]!r} action_points={n}")
            retained.append(art)
        if art.doi:
            store.mark_seen(art.doi, area.slug)

    dropped = len(new_articles) - len(retained)
    console.print(f"  retained={len(retained)} dropped={dropped} threshold={threshold}")

    # ── 6. Update state ────────────────────────────────────────────────────
    store.finish_run(run_id, ingested=len(merged), retained=len(retained), dropped=dropped)
    if truncated:
        console.print("  [yellow]  truncated run — last_run left unchanged[/]")
    else:
        store.set_last_run(area.slug)
    return retained


def run_all(
    settings: Settings | None = None,
    only_area: str | None = None,
    limit: int | None = None,
    debug: bool = False,
) -> Path:
    """Run the pipeline for every configured area and render reports.

    Returns the path to the generated `index.html`.
    """
    settings = settings or Settings()
    areas_file = load_areas(settings.areas_config)
    org_context = load_org_context(settings.org_context)
    loaded_areas = discover_areas(settings, areas_file)

    # Construct clients once, share across areas
    llm = LLMClient(settings)
    screener = Screener(llm)
    summarizer = Summarizer(llm)
    email_source = ScopusEmailSource(settings)
    scopus_api = ScopusApiSource(settings)
    openalex = OpenAlexSource(settings)
    crossref = CrossrefSource(settings)
    deduper = Deduper()

    renderer = ReportRenderer(
        templates_dir=Path(__file__).resolve().parent.parent.parent / "templates",
        output_dir=settings.data_dir / "reports",
    )

    index_rows: list[AreaIndexRow] = []
    with Store(settings.data_dir / "state.db") as store:
        for area in loaded_areas:
            if only_area and area.slug != only_area:
                continue
            threshold = areas_file.threshold_for(area.config)
            retained = run_area(
                area,
                settings,
                store,
                threshold,
                org_context,
                screener,
                summarizer,
                email_source,
                scopus_api,
                openalex,
                crossref,
                deduper,
                limit=limit,
                debug=debug,
            )
            renderer.render_area(area, retained, threshold)
            index_rows.append(
                AreaIndexRow(
                    slug=area.slug,
                    name=area.name,
                    last_run=store.get_last_run(area.slug),
                    article_count=len(retained),
                    threshold=threshold,
                )
            )

    index_path = renderer.render_index(index_rows)
    console.print(f"[bold green]Reports written to[/] {index_path.parent}")
    console.print(f"  open {index_path}")
    return index_path
