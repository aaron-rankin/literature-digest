"""Local fixture source for fully-offline pipeline runs.

Reads normalized `Article` JSON from `<fixtures_dir>/<area_slug>/*.json` so the
pipeline can be exercised end-to-end without calling Scopus / OpenAlex /
Crossref. Used by `literature-digest run --local` for cheap, deterministic
debugging of the dedupe -> screen -> summarize -> render stages without burning
external API quota.

Each JSON file is either a single article object or a list of them, matching the
`Article` model's fields, e.g.:

    {"doi": "10.1234/abcd", "title": "...", "abstract": "...",
     "authors": ["Smith, J."], "journal": "J. Sports Sci.", "year": 2025}

The date window is ignored — fixtures are replayed in full on every run.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from literature_digest.config import AreaConfig, Settings
from literature_digest.models import Article

_SOURCE = "fixture"


class LocalSource:
    """Reads Article fixtures from disk instead of hitting a network API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _area_dir(self, area_slug: str) -> Path:
        return self.settings.fixtures_dir / area_slug

    def search(self, area: AreaConfig, since: datetime | None) -> list[Article]:
        """Return every fixture article for `area`. `since` is ignored."""
        _ = since  # fixtures are replayed in full regardless of the date window
        area_dir = self._area_dir(area.slug)
        if not area_dir.is_dir():
            return []
        articles: list[Article] = []
        for path in sorted(area_dir.glob("*.json")):
            articles.extend(_load(path, area.slug))
        return articles

    def enrich(self, doi: str) -> Article | None:
        """No-op: offline mode does no metadata enrichment."""
        _ = doi
        return None


def _load(path: Path, area_slug: str) -> list[Article]:
    """Parse one fixture file (object or list) into `Article`s."""
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
