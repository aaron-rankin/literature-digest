"""Local fixture source for fully-offline pipeline runs.

Reads normalized ``Article`` JSON from ``<fixtures_dir>/<area_slug>/*.json`` so
the pipeline can be exercised end-to-end without calling Scopus / OpenAlex /
Crossref. Used by ``literature-digest run --local`` for cheap, deterministic
debugging of the dedupe -> screen -> summarize -> render stages.

The date window is ignored — fixtures are replayed in full on every run.
"""

from __future__ import annotations

import json
from pathlib import Path

from literature_digest.config import Settings
from literature_digest.models import Article
from literature_digest.query import DateWindow, SourceQuery

_SOURCE = "fixture"


class LocalSource:
    """Reads Article fixtures from disk instead of hitting a network API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _area_dir(self, area_slug: str) -> Path:
        return self.settings.fixtures_dir / area_slug

    def search(self, source_query: SourceQuery, window: DateWindow | None = None) -> list[Article]:
        """Return fixture articles for ``source_query.area_slug`` matching the term.

        Fixtures whose ``matched_terms`` include ``source_query.term_name`` are
        returned; fixtures without ``matched_terms`` are included for every term
        (useful for quick smoke tests). The date window is ignored.
        """
        _ = window  # fixtures are replayed regardless of the date window
        area_dir = self._area_dir(source_query.area_slug)
        if not area_dir.is_dir():
            return []

        articles: list[Article] = []
        for path in sorted(area_dir.glob("*.json")):
            for art in _load(path, source_query.area_slug):
                if not art.matched_terms or source_query.term_name in art.matched_terms:
                    # Ensure the term that surfaced the fixture is present.
                    if source_query.term_name not in art.matched_terms:
                        art.matched_terms = [*art.matched_terms, source_query.term_name]
                    articles.append(art)
        return articles

    def enrich(self, doi: str) -> Article | None:
        """No-op: offline mode does no metadata enrichment."""
        _ = doi
        return None


def _load(path: Path, area_slug: str) -> list[Article]:
    """Parse one fixture file (object or list) into ``Article`` objects."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    records = raw if isinstance(raw, list) else [raw]
    out: list[Article] = []
    for rec in records:
        art = Article.model_validate(rec)
        if _SOURCE not in art.sources:
            art.sources = [*art.sources, _SOURCE]
        art.area_slug = art.area_slug or area_slug
        out.append(art)
    return out
