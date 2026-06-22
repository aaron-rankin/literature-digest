"""OpenAlex API client (free, no key, polite pool via mailto).

Contract:
    search(area: AreaConfig, since: datetime) -> list[Article]
    enrich(doi: str) -> Article | None

Uses `https://api.openalex.org/works` with `mailto=` in the query string to
join the polite pool (faster rate limits). Returns metadata + the inverted-
index abstract reconstructed into prose.

Phase 2 will implement:
- httpx client with `mailto` param
- Keyword search: `?search=<keywords>&filter=from_publication_date:<since>`
- DOI lookup: `?filter=doi:<doi>`
- Reconstruction of abstract from `abstract_inverted_index`
"""

from __future__ import annotations

from datetime import datetime

from literature_digest.config import AreaConfig, Settings
from literature_digest.models import Article


class OpenAlexSource:
    """OpenAlex API client. Placeholder body."""

    BASE_URL = "https://api.openalex.org/works"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search(self, area: AreaConfig, since: datetime | None) -> list[Article]:
        """Search OpenAlex by `area.keywords` since `since`. PLACEHOLDER: returns []."""
        # TODO(phase-2): build search query, paginate via cursor, reconstruct abstract
        return []

    def enrich(self, doi: str) -> Article | None:
        """Lookup a single DOI on OpenAlex. PLACEHOLDER: returns None."""
        # TODO(phase-2): filter=doi:<doi>, parse, reconstruct abstract
        return None
