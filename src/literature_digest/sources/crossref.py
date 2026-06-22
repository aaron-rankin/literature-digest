"""Crossref API client (free, polite pool via mailto).

Contract:
    search(area: AreaConfig, since: datetime) -> list[Article]
    enrich(doi: str) -> Article | None

Uses `https://api.crossref.org/works` with `mailto=` header to join the polite
pool. Returns metadata + abstract when Crossref has it (rare, but free).

Phase 2 will implement:
- httpx client with `User-Agent: literature-digest/0.1 (mailto:...)`
- Keyword search: `?query=<keywords>&filter=from-pub-date:<since>`
- DOI lookup: `https://api.crossref.org/works/<doi>`
"""

from __future__ import annotations

from datetime import datetime

from literature_digest.config import AreaConfig, Settings
from literature_digest.models import Article


class CrossrefSource:
    """Crossref API client. Placeholder body."""

    BASE_URL = "https://api.crossref.org/works"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search(self, area: AreaConfig, since: datetime | None) -> list[Article]:
        """Search Crossref by `area.keywords` since `since`. PLACEHOLDER: returns []."""
        # TODO(phase-2): build query, paginate via cursor, parse
        return []

    def enrich(self, doi: str) -> Article | None:
        """Lookup a single DOI on Crossref. PLACEHOLDER: returns None."""
        # TODO(phase-2): GET /works/<doi>, parse
        return None
