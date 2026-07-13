"""Pipeline orchestrator: wires sources -> dedupe -> screen -> summarize -> render."""

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
from literature_digest.query import DateWindow, SourceQuery, compute_date_window
from literature_digest.report import AreaIndexRow, ReportRenderer
from literature_digest.screen import LLMClient, Screener
from literature_digest.sources import (
    CrossrefSource,
    Deduper,
    LocalSource,
    OpenAlexSource,
    ScopusApiSource,
    ScopusEmailSource,
)
from literature_digest.store import Store
from literature_digest.summarize import Summarizer

console = Console()


def _safe_fetch(label: str, fn: Callable[[], list[Article]]) -> list[Article]:
    """Run one source fetch, downgrading network failures to an empty result."""
    try:
        return fn()
    except httpx.HTTPError as exc:
        console.print(f"[yellow]  {label} unavailable: {exc!r} — skipping[/]")
        return []


def _tag_area(articles: list[Article], area_slug: str) -> None:
    for art in articles:
        art.area_slug = area_slug


def run_area(
    area: LoadedArea,
    settings: Settings,
    store: Store,
    areas_file,
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
    local: bool = False,
    local_source: LocalSource | None = None,
    sources: set[str] | None = None,
) -> list[Article]:
    """Run the full pipeline for a single area. Returns retained articles.

    ``sources`` restricts which network sources are used in non-local mode.
    Defaults to all sources. Local mode ignores this and uses fixtures only.
    """
    last_run = store.get_last_run(area.slug)
    run_id = store.start_run(area.slug)
    console.print(f"[bold blue]#{area.slug}[/] since={last_run or 'first run'}")

    # ── 1. Fetch ───────────────────────────────────────────────────────────
    all_articles: list[Article] = []

    if local:
        assert local_source is not None
        for term in area.terms:
            sq = SourceQuery(term_name=term.name, parsed=term.parsed, area_slug=area.slug)
            fetched = local_source.search(sq, DateWindow())
            _tag_area(fetched, area.slug)
            all_articles.extend(fetched)
            console.print(f"  [magenta]local[/] {term.name}: {len(fetched)}")
    else:
        sources = sources or {"scopus", "openalex", "crossref", "email"}

        from_email: list[Article] = []
        if "email" in sources:
            from_email = _safe_fetch(
                "scopus_email", lambda: email_source.fetch_articles(area, last_run)
            )
            _tag_area(from_email, area.slug)

        lookback = areas_file.lookback_days()
        first_run_lookback = areas_file.first_run_lookback_days()

        for term in area.terms:
            window = compute_date_window(
                last_run=last_run,
                lookback_days=lookback,
                first_run_lookback_days=first_run_lookback,
                pubyear_from=term.parsed.pubyear_from,
                pubyear_to=term.parsed.pubyear_to,
            )
            sq = SourceQuery(term_name=term.name, parsed=term.parsed, area_slug=area.slug)

            console.print(f"  [dim]{term.name}[/] query={sq.parsed.terms}")
            counts: dict[str, int] = {}
            if "scopus" in sources:
                from_scopus = _safe_fetch(
                    f"scopus/{term.name}",
                    lambda sq=sq, window=window: scopus_api.search(sq, window),
                )
                all_articles.extend(from_scopus)
                counts["scopus"] = len(from_scopus)
            if "openalex" in sources:
                from_openalex = _safe_fetch(
                    f"openalex/{term.name}",
                    lambda sq=sq, window=window: openalex.search(sq, window),
                )
                all_articles.extend(from_openalex)
                counts["openalex"] = len(from_openalex)
            if "crossref" in sources:
                from_crossref = _safe_fetch(
                    f"crossref/{term.name}",
                    lambda sq=sq, window=window: crossref.search(sq, window),
                )
                all_articles.extend(from_crossref)
                counts["crossref"] = len(from_crossref)

            console.print("    fetched: " + " ".join(f"{k}={v}" for k, v in counts.items()))

        # Enrich email-extracted DOIs via enabled sources.
        enriched = []
        for stub in from_email:
            if stub.doi:
                art = stub
                if "scopus" in sources:
                    art = scopus_api.enrich(stub.doi) or art
                if "openalex" in sources and art is stub:
                    art = openalex.enrich(stub.doi) or art
                enriched.append(art)
            else:
                enriched.append(stub)
        all_articles = enriched + all_articles

    # ── 2. Dedupe & merge ──────────────────────────────────────────────────
    merged = deduper.dedupe(all_articles)
    for a in merged:
        a.area_slug = area.slug
    console.print(f"  deduped: {len(all_articles)} -> {len(merged)}")

    # ── 3. Filter already-seen (skipped in local mode so fixtures replay) ───
    if local:
        new_articles = merged
    else:
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
        if art.doi and not local:
            store.mark_seen(art.doi, area.slug)

    dropped = len(new_articles) - len(retained)
    console.print(f"  retained={len(retained)} dropped={dropped} threshold={threshold}")

    # ── 6. Update state ────────────────────────────────────────────────────
    store.finish_run(run_id, ingested=len(merged), retained=len(retained), dropped=dropped)
    if local:
        console.print("  [magenta]  local mode — last_run left unchanged[/]")
    elif truncated:
        console.print("  [yellow]  truncated run — last_run left unchanged[/]")
    else:
        store.set_last_run(area.slug)
    return retained


def run_all(
    settings: Settings | None = None,
    only_area: str | None = None,
    limit: int | None = None,
    debug: bool = False,
    local: bool = False,
    fast: bool = False,
    sources: set[str] | None = None,
) -> Path:
    """Run the pipeline for every configured area and render reports.

    ``local=True`` runs fully offline from ``settings.fixtures_dir`` fixtures and
    writes state to a separate ``state.local.db``, leaving the production
    ``state.db`` untouched.

    ``fast=True`` swaps in ``settings.lit_fast_model`` and writes to
    ``state.test.db`` so test scores never mix with prod scores.

    ``sources`` restricts which network sources to use in non-local mode
    (e.g. ``{"scopus"}`` for a Scopus-only run). Ignored when ``local=True``.
    """
    settings = settings or Settings()
    areas_file = load_areas(settings.areas_config)
    org_context = load_org_context(settings.org_context)
    loaded_areas = discover_areas(settings, areas_file)

    llm = LLMClient(
        settings,
        model=settings.lit_fast_model if fast else None,
        api_base=settings.lit_fast_api_base if fast else None,
    )
    screener = Screener(llm)
    summarizer = Summarizer(llm)
    email_source = ScopusEmailSource(settings)
    scopus_api = ScopusApiSource(settings)
    openalex = OpenAlexSource(settings)
    crossref = CrossrefSource(settings)
    local_source = LocalSource(settings)
    deduper = Deduper()

    renderer = ReportRenderer(
        templates_dir=Path(__file__).resolve().parent.parent.parent / "templates",
        output_dir=settings.data_dir / "reports",
    )

    if local:
        db_name = "state.local.db"
    elif fast:
        db_name = "state.test.db"
    else:
        db_name = "state.db"
    index_rows: list[AreaIndexRow] = []
    with Store(settings.data_dir / db_name) as store:
        for area in loaded_areas:
            if only_area and area.slug != only_area:
                continue
            threshold = areas_file.threshold_for(area.config)
            retained = run_area(
                area,
                settings,
                store,
                areas_file,
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
                local=local,
                local_source=local_source,
                sources=sources,
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
