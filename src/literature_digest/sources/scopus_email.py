"""Scopus alert email ingestion via IMAP — not implemented.

The pipeline uses direct Scopus API search instead of email alerts.
This source is intentionally a no-op and is excluded from Phase 3.
"""

from __future__ import annotations

from datetime import datetime

from literature_digest.config import LoadedArea, Settings
from literature_digest.models import Article


class ScopusEmailSource:
    """IMAP fetcher for Scopus alert emails — not used."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def fetch_articles(self, area: LoadedArea, since: datetime | None) -> list[Article]:
        return []
