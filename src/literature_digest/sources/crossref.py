"""Crossref API client (free, polite pool via mailto).

Contract:
    search(area: AreaConfig, since: datetime | None) -> list[Article]
    enrich(doi: str) -> Article | None

Uses `https://api.crossref.org/works` with a polite-pool `User-Agent` (and
`mailto` param) to get better rate limits. Keyword search uses Crossref's
free-text `query` with a `from-pub-date` filter; results are deep-paged via the
`cursor` mechanism. Abstracts, when present, arrive as JATS XML and are stripped
to plain text.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import httpx

from literature_digest.config import AreaConfig, Settings
from literature_digest.models import Article
from literature_digest.sources.dedupe import normalize_doi

_SOURCE = "crossref"
_ROWS = 100
_TIMEOUT = 30.0
_JATS_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


class CrossrefSource:
    """Crossref API client."""

    BASE_URL = "https://api.crossref.org/works"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ── public API ─────────────────────────────────────────────────────────
    def search(self, area: AreaConfig, since: datetime | None) -> list[Article]:
        """Search Crossref for `area.keywords` published since `since`."""
        params: dict[str, Any] = {
            "query": " ".join(area.keywords),
            "rows": _ROWS,
            "cursor": "*",
        }
        if since is not None:
            params["filter"] = f"from-pub-date:{since.date().isoformat()}"
        self._add_mailto(params)

        articles: list[Article] = []
        with httpx.Client(timeout=_TIMEOUT, headers=self._headers()) as client:
            while True:
                message = self._get(client, self.BASE_URL, params).get("message", {})
                items = message.get("items", [])
                articles.extend(_parse_item(it) for it in items)
                next_cursor = message.get("next-cursor")
                if not items or not next_cursor:
                    break
                params["cursor"] = next_cursor
        return articles

    def enrich(self, doi: str) -> Article | None:
        """Look up a single DOI on Crossref. Returns None if not found."""
        norm = normalize_doi(doi)
        if not norm:
            return None
        params: dict[str, Any] = {}
        self._add_mailto(params)
        with httpx.Client(timeout=_TIMEOUT, headers=self._headers()) as client:
            resp = client.get(f"{self.BASE_URL}/{norm}", params=params)
            if resp.status_code == httpx.codes.NOT_FOUND:
                return None
            resp.raise_for_status()
            return _parse_item(resp.json().get("message", {}))

    # ── helpers ────────────────────────────────────────────────────────────
    @staticmethod
    def _get(client: httpx.Client, url: str, params: dict[str, Any]) -> dict[str, Any]:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def _add_mailto(self, params: dict[str, Any]) -> None:
        if self.settings.contact_email:
            params["mailto"] = self.settings.contact_email

    def _headers(self) -> dict[str, str]:
        contact = f" (mailto:{self.settings.contact_email})" if self.settings.contact_email else ""
        return {"User-Agent": f"literature-digest/0.1{contact}"}


# ── module-level parsing helpers ───────────────────────────────────────────
def _strip_jats(abstract: str | None) -> str | None:
    """Strip JATS XML tags from a Crossref abstract, collapsing whitespace."""
    if not abstract:
        return None
    text = _WS.sub(" ", _JATS_TAG.sub(" ", abstract)).strip()
    return text or None


def _first(seq: list[Any] | None) -> Any | None:
    return seq[0] if seq else None


def _parse_item(item: dict[str, Any]) -> Article:
    """Map a Crossref `message` item onto our Article model."""
    authors = [
        name
        for a in item.get("author", [])
        if (name := f"{a.get('given', '')} {a.get('family', '')}".strip())
    ]
    doi = item.get("DOI")
    date_parts = (item.get("issued") or {}).get("date-parts") or [[]]
    year = date_parts[0][0] if date_parts[0] else None

    return Article(
        doi=normalize_doi(doi),
        title=_first(item.get("title")),
        abstract=_strip_jats(item.get("abstract")),
        authors=authors,
        journal=_first(item.get("container-title")),
        year=year,
        url=item.get("URL") or (f"https://doi.org/{doi}" if doi else None),
        pub_date=_parse_pub_date(date_parts[0]),
        sources=[_SOURCE],
    )


def _parse_pub_date(parts: list[int]) -> datetime | None:
    """Build a datetime from Crossref `date-parts` (year[, month[, day]])."""
    if not parts:
        return None
    year = parts[0]
    month = parts[1] if len(parts) > 1 else 1
    day = parts[2] if len(parts) > 2 else 1
    try:
        return datetime(year, month, day)
    except (ValueError, TypeError):
        return None
