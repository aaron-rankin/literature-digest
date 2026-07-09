"""Elsevier Scopus Search API enrichment.

Contract:
    enrich(doi: str) -> Article | None           # metadata by DOI
    search(area: AreaConfig, since: datetime) -> list[Article]   # by Scopus query

Uses `https://api.elsevier.com/content/search/scopus` with the configured
`SCOPUS_API_KEY` (and optional inst token). Returns authoritative metadata:
title, abstract, authors, journal, year, DOI.

Phase 3 will implement:
- httpx client with `apikey` / `insttoken` / `Accept` headers
- Query construction from `area.scopus_query` + date range
- Backoff on 429 (rate limit) - Scopus is strict on quotas
"""

from __future__ import annotations

from datetime import datetime

from literature_digest.config import LoadedArea, Settings
from literature_digest.models import Article


class ScopusApiSource:
    """Elsevier Scopus Search API client. Placeholder body."""

    BASE_URL = "https://api.elsevier.com/content/search/scopus"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def enrich(self, doi: str) -> Article | None:
        """Enrich a single DOI with Scopus metadata. PLACEHOLDER: returns None."""
        # TODO(phase-3): GET ?query=DOI(<doi>) and parse the response
        return None

    def search(self, area: LoadedArea, since: datetime | None) -> list[Article]:
        """Search Scopus by `area.scopus_query` since `since`. PLACEHOLDER: returns []."""
        # TODO(phase-3): build query with PUBDATETIME filter, paginate, parse
        return []
