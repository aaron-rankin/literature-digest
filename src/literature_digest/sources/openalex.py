"""OpenAlex API client (free, no key, polite pool via mailto).

Contract:
    search(area: LoadedArea, since: datetime | None) -> list[Article]
    enrich(doi: str) -> Article | None

Uses `https://api.openalex.org/works` with `mailto=` in the query string to join
the polite pool (faster, more reliable rate limits). Searches each parsed term
independently (OR of that term's quoted keywords) plus a `from_publication_date`
filter, then deduplicates by DOI. Abstracts are reconstructed from OpenAlex's
`abstract_inverted_index` back into prose.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from literature_digest.config import LoadedArea, Settings
from literature_digest.models import Article
from literature_digest.query import UnsupportedScopusSyntax, parse
from literature_digest.sources.dedupe import normalize_doi

_SOURCE = "openalex"
_PER_PAGE = 100
_TIMEOUT = 30.0


class OpenAlexSource:
    """OpenAlex API client."""

    BASE_URL = "https://api.openalex.org/works"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ── public API ─────────────────────────────────────────────────────────
    def search(self, area: LoadedArea, since: datetime | None) -> list[Article]:
        """Search OpenAlex for each term in `area` and deduplicate by DOI."""
        seen: set[str] = set()
        articles: list[Article] = []
        for term in area.terms:
            parsed = term.parsed
            if parsed is None:
                try:
                    parsed = parse(term.raw_query, term_name=term.name)
                except UnsupportedScopusSyntax:
                    continue
            if not parsed.terms:
                continue
            for art in self._search_keywords(parsed.terms, since):
                if art.doi and art.doi in seen:
                    continue
                if art.doi:
                    seen.add(art.doi)
                articles.append(art)
        return articles

    def _search_keywords(self, keywords: list[str], since: datetime | None) -> list[Article]:
        """Search OpenAlex for one keyword list published since `since`."""
        params: dict[str, Any] = {
            "search": _boolean_query(keywords),
            "per-page": _PER_PAGE,
            "cursor": "*",
        }
        if since is not None:
            params["filter"] = f"from_publication_date:{since.date().isoformat()}"
        self._add_mailto(params)

        articles: list[Article] = []
        with httpx.Client(timeout=_TIMEOUT, headers=self._headers()) as client:
            while True:
                data = self._get(client, self.BASE_URL, params)
                results = data.get("results", [])
                articles.extend(_parse_work(w) for w in results)
                next_cursor = (data.get("meta") or {}).get("next_cursor")
                if not results or not next_cursor:
                    break
                params["cursor"] = next_cursor
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
    @staticmethod
    def _get(client: httpx.Client, url: str, params: dict[str, Any]) -> dict[str, Any]:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def _add_mailto(self, params: dict[str, Any]) -> None:
        if self.settings.contact_email:
            params["mailto"] = self.settings.contact_email

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": _user_agent(self.settings)}


# ── module-level parsing helpers ───────────────────────────────────────────
def _boolean_query(keywords: list[str]) -> str:
    """OR of quoted keyword phrases for OpenAlex's boolean `search` param."""
    return " OR ".join(f'"{kw}"' for kw in keywords)


def _user_agent(settings: Settings) -> str:
    contact = f" (mailto:{settings.contact_email})" if settings.contact_email else ""
    return f"literature-digest/0.1{contact}"


def _reconstruct_abstract(inverted: dict[str, list[int]] | None) -> str | None:
    """Rebuild prose from OpenAlex's `abstract_inverted_index` (word -> positions)."""
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
    """Map an OpenAlex `work` object onto our Article model."""
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
