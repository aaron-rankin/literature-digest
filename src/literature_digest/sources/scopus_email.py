"""Scopus alert email ingestion via IMAP.

Contract:
    fetch_articles(area, since) -> list[Article]

Connects to the configured IMAP inbox, searches unread emails from Scopus
matching `area.scopus_query`, extracts DOIs from the body, and returns stub
Articles carrying just the DOI plus provenance. The Scopus API source then
enriches these stubs with full metadata and abstract.

Phase 3 will implement:
- imap_tools.MailBox connection with the configured host/user/password
- Sender + subject filtering to identify Scopus alert emails
- Regex extraction of `doi.org/10.*` and `scopus.com/url?*` links from HTML bodies
- Move processed messages to the configured IMAP folder (never delete)
"""

from __future__ import annotations

from datetime import datetime

from literature_digest.config import AreaConfig, Settings
from literature_digest.models import Article


class ScopusEmailSource:
    """IMAP fetcher for Scopus alert emails. Placeholder body."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def fetch_articles(self, area: AreaConfig, since: datetime | None) -> list[Article]:
        """Return articles parsed from Scopus alert emails for `area`.

        PLACEHOLDER: returns an empty list. Phase 3 will implement IMAP fetch +
        DOI extraction. Each returned Article has `doi` set, `sources=["scopus_email"]`,
        and `area_slug=area.slug`.
        """
        # TODO(phase-3): implement IMAP fetch + body parsing
        return []
