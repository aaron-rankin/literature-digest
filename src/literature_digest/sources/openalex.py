"""OpenAlex API client (free, no key, polite pool via mailto).

Contract:
    search(source_query: SourceQuery, window: DateWindow) -> list[Article]
    enrich(doi: str) -> Article | None

Uses ``https://api.openalex.org/works`` with ``mailto=`` in the query string to
join the polite pool. The pipeline now calls this once per search term, so the
query is rendered from the parsed Scopus-subset tree and the crawl window uses
``from_created_date`` while ``PUBYEAR`` maps to ``from_publication_date``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from literature_digest.config import Settings
from literature_digest.models import Article
from literature_digest.query import DateWindow, QueryTranslator, SourceQuery
from literature_digest.sources.dedupe import normalize_doi

_SOURCE = "openalex"
_PER_PAGE = 100
_TIMEOUT = 30.0


class OpenAlexSource:
    """OpenAlex API client."""

    BASE_URL = "https://api.openalex.org/works"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._translator = QueryTranslator()

    # ── public API ─────────────────────────────────────────────────────────
    def search(self, source_query: SourceQuery, window: DateWindow) -> list[Article]:
        """Search OpenAlex for a single term and return parsed articles."""
        params = self._translator.to_openalex(source_query, window)
        self._add_mailto(params)
        articles = self._search_params(params)
        for art in articles:
            art.matched_terms = [source_query.term_name]
        return articles

    def enrich(self, doi: str) -> Article | None:
        """Look up a single DOI on OpenAlex. Returns None if not found."""
        norm = normalize_doi(doi)
        if not norm:
            return None
        params: dict[str, Any] = {}
        self._add_mailto(params)
        url = f"{self.BASE_URL}/https://doi.org/{norm}"
        with httpx.Client(timeout=_TIMEOUT, headers=self._headers()) as client:
            resp = client.get(url, params=params)
            if resp.status_code == httpx.codes.NOT_FOUND:
                return None
            resp.raise_for_status()
            return _parse_work(resp.json())

    # ── helpers ────────────────────────────────────────────────────────────
    def _search_params(self, params: dict[str, Any]) -> list[Article]:
        """Paginate through an OpenAlex params dict."""
        articles: list[Article] = []
        with httpx.Client(timeout=_TIMEOUT, headers=self._headers()) as client:
            while True:
                resp = client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                articles.extend(_parse_work(w) for w in results)
                next_cursor = (data.get("meta") or {}).get("next_cursor")
                if not results or not next_cursor:
                    break
                params["cursor"] = next_cursor
        return articles

    def _add_mailto(self, params: dict[str, Any]) -> None:
        if self.settings.contact_email:
            params["mailto"] = self.settings.contact_email

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": _user_agent(self.settings)}


# ── module-level parsing helpers ───────────────────────────────────────────
def _user_agent(settings: Settings) -> str:
    contact = f" (mailto:{settings.contact_email})" if settings.contact_email else ""
    return f"literature-digest/0.1{contact}"


def _reconstruct_abstract(inverted: dict[str, list[int]] | None) -> str | None:
    """Rebuild prose from OpenAlex's ``abstract_inverted_index``."""
    if not inverted:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions[i] = word
    if not positions:
        return None
    return " ".join(positions[i] for i in sorted(positions))


def _parse_work(work: dict[str, Any]) -> Article:
    """Map an OpenAlex ``work`` object onto our Article model."""
    authors = [
        a["author"]["display_name"]
        for a in work.get("authorships", [])
        if a.get("author", {}).get("display_name")
    ]
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    pub_date = work.get("publication_date")

    return Article(
        doi=normalize_doi(work.get("doi")),
        title=work.get("display_name"),
        abstract=_reconstruct_abstract(work.get("abstract_inverted_index")),
        authors=authors,
        journal=source.get("display_name"),
        year=work.get("publication_year"),
        url=work.get("doi") or primary.get("landing_page_url") or work.get("id"),
        pub_date=datetime.fromisoformat(pub_date) if pub_date else None,
        sources=[_SOURCE],
    )
