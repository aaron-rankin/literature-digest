"""Elsevier Scopus Search API client.

Contract:
    search(source_query: SourceQuery, window: DateWindow) -> list[Article]
    enrich(doi: str) -> Article | None

Uses ``https://api.elsevier.com/content/search/scopus`` with the configured
``SCOPUS_API_KEY`` (and optional inst token). The query is built from the parsed
Scopus-subset tree so it round-trips the authored query, then the crawl window is
injected as ``ORIG-LOAD-DATE`` and ``PUBYEAR`` is preserved.

Search results are fetched with ``view=STANDARD`` (25/page). Because the standard
view often omits abstracts, we attempt to backfill missing abstracts via the
Abstract Retrieval API (``/content/abstract/doi/{doi}``) when a DOI is present.
"""

from __future__ import annotations

import random
import time
from datetime import datetime
from typing import Any

import httpx

from literature_digest.config import Settings
from literature_digest.models import Article
from literature_digest.query import DateWindow, QueryTranslator, SourceQuery
from literature_digest.sources.dedupe import normalize_doi

_SOURCE = "scopus"
_BASE_SEARCH = "https://api.elsevier.com/content/search/scopus"
_BASE_ABSTRACT = "https://api.elsevier.com/content/abstract/doi"
_TIMEOUT = 30.0
_MAX_RETRIES = 4
_PAGE_SIZE = 25
_ABSTRACT_BACKFILL_LIMIT = 25
_BACKOFF_BASE = 1.0
_BACKOFF_CAP = 60.0


class ScopusQuotaError(httpx.HTTPError):
    """Raised when Scopus quota is exhausted after all retries."""


class ScopusApiSource:
    """Elsevier Scopus Search API client."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._translator = QueryTranslator()

    # ── public API ─────────────────────────────────────────────────────────
    def search(self, source_query: SourceQuery, window: DateWindow) -> list[Article]:
        """Search Scopus for a single term and return parsed articles."""
        query = self._translator.to_scopus(source_query, window)
        params: dict[str, Any] = {
            "query": query,
            "view": "STANDARD",
            "count": _PAGE_SIZE,
            "start": 0,
        }

        articles: list[Article] = []
        with httpx.Client(timeout=_TIMEOUT, headers=self._headers()) as client:
            start = 0
            while True:
                params["start"] = start
                data = self._get_with_retry(client, _BASE_SEARCH, params)
                results = data.get("search-results", {})
                entries = results.get("entry", [])
                articles.extend(self._parse_entry(e) for e in entries)

                total = _int_or_none(results.get("opensearch:totalResults"))
                if total is None:
                    break
                start += len(entries)
                if start >= total or not entries:
                    break

        for art in articles:
            art.matched_terms = [source_query.term_name]

        # Backfill abstracts via the Abstract Retrieval API when possible.
        self._enrich_abstracts(articles)
        return articles

    def enrich(self, doi: str) -> Article | None:
        """Enrich a single DOI with Scopus metadata."""
        norm = normalize_doi(doi)
        if not norm:
            return None
        return self._fetch_abstract(norm)

    # ── network helpers ────────────────────────────────────────────────────
    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "X-ELS-APIKey": self.settings.scopus_api_key,
        }
        if self.settings.scopus_inst_token:
            headers["X-ELS-Insttoken"] = self.settings.scopus_inst_token
        return headers

    def _get_with_retry(
        self,
        client: httpx.Client,
        url: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """GET with exponential backoff on 429 / quota-exhausted headers."""
        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            resp = client.get(url, params=params)
            remaining = _int_or_none(resp.headers.get("X-RateLimit-Remaining"))
            # If the header explicitly says 0, treat as rate-limit even on a 200.
            if remaining is not None and remaining <= 0:
                resp.status_code = 429  # force retry path
            if resp.status_code < 400:
                return resp.json()
            if resp.status_code != 429:
                resp.raise_for_status()

            last_error = httpx.HTTPStatusError(
                "Scopus rate limit (429)",
                request=resp.request,
                response=resp,
            )
            if attempt == _MAX_RETRIES:
                break
            delay = min(_BACKOFF_BASE * (2**attempt) + random.uniform(0, 1), _BACKOFF_CAP)
            time.sleep(delay)

        raise ScopusQuotaError(
            f"Scopus quota exhausted after {_MAX_RETRIES + 1} attempts"
        ) from last_error

    # ── parsing ────────────────────────────────────────────────────────────
    def _parse_entry(self, entry: dict[str, Any]) -> Article:
        """Map one Scopus search ``entry`` to an ``Article``."""
        doi = normalize_doi(entry.get("prism:doi"))
        cover = entry.get("prism:coverDate")
        year = _year_from_date(cover)

        authors: list[str] = []
        for a in entry.get("author", []):
            name = a.get("authname") or a.get("preferred-name", {}).get("ce:indexed-name")
            if name:
                authors.append(name)
        if not authors:
            creator = entry.get("dc:creator")
            if creator:
                authors = [creator]

        return Article(
            doi=doi,
            title=entry.get("dc:title"),
            abstract=entry.get("dc:description"),
            authors=authors,
            journal=entry.get("prism:publicationName"),
            year=year,
            url=(f"https://doi.org/{doi}" if doi else None),
            pub_date=_parse_date(cover),
            sources=[_SOURCE],
        )

    def _enrich_abstracts(self, articles: list[Article]) -> None:
        """Backfill missing abstracts from the Abstract Retrieval API.

        To avoid burning quota on hundreds of search results, only the first
        ``_ABSTRACT_BACKFILL_LIMIT`` articles without abstracts are enriched.
        """
        if not self.settings.scopus_api_key:
            return
        missing = [a for a in articles if not a.abstract and a.doi]
        missing = missing[:_ABSTRACT_BACKFILL_LIMIT]
        with httpx.Client(timeout=_TIMEOUT, headers=self._headers()) as client:
            for art in missing:
                enriched = self._fetch_abstract(art.doi, client=client)
                if enriched and enriched.abstract:
                    art.abstract = enriched.abstract

    def _fetch_abstract(
        self,
        doi: str,
        client: httpx.Client | None = None,
    ) -> Article | None:
        """Fetch one article via the Abstract Retrieval API."""
        url = f"{_BASE_ABSTRACT}/{doi}"
        close_client = client is None
        try:
            client = client or httpx.Client(timeout=_TIMEOUT, headers=self._headers())
            data = self._get_with_retry(client, url, {})
        except httpx.HTTPError:
            return None
        finally:
            if close_client:
                client.close()
        return _parse_abstract_response(data)


# ── module-level helpers ───────────────────────────────────────────────────
def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _year_from_date(text: str | None) -> int | None:
    if not text:
        return None
    try:
        return int(text[:4])
    except (ValueError, TypeError):
        return None


def _parse_date(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")  # noqa: DTZ007
    except ValueError:
        return None


def _parse_abstract_response(data: dict[str, Any]) -> Article | None:
    """Extract metadata from an Abstract Retrieval API response."""
    root = data.get("abstracts-retrieval-response", data)
    coredata = root.get("coredata", {})
    item = root.get("item", {})
    bibrecord = item.get("bibrecord", {})
    head = bibrecord.get("head", {})

    doi = normalize_doi(coredata.get("prism:doi"))
    title = coredata.get("dc:title") or _deep_get(head, "citation-title")
    abstract = coredata.get("dc:description") or _extract_abstract_text(head.get("abstracts"))
    journal = coredata.get("prism:publicationName")
    cover = coredata.get("prism:coverDate")

    authors: list[str] = []
    for a in coredata.get("dc:creator", []):
        name = a if isinstance(a, str) else a.get("$", a.get("ce:indexed-name"))
        if name:
            authors.append(name)
    if not authors:
        authors = _authors_from_abstracts(root)

    return Article(
        doi=doi,
        title=title,
        abstract=abstract,
        authors=authors,
        journal=journal,
        year=_year_from_date(cover),
        url=(f"https://doi.org/{doi}" if doi else None),
        pub_date=_parse_date(cover),
        sources=[_SOURCE],
    )


def _extract_abstract_text(abstracts: Any) -> str | None:
    if not abstracts:
        return None
    if isinstance(abstracts, dict):
        abstract = abstracts.get("abstract")
        if isinstance(abstract, dict):
            return abstract.get("ce:para") or abstract.get("$")
        return abstract
    if isinstance(abstracts, list):
        return _extract_abstract_text(abstracts[0]) if abstracts else None
    return None


def _authors_from_abstracts(root: dict[str, Any] | None) -> list[str]:
    if not isinstance(root, dict):
        return []
    authors = (root.get("authors") or {}).get("author", [])
    out: list[str] = []
    for a in authors:
        name = a.get("preferred-name", {}).get("ce:indexed-name") or a.get("ce:indexed-name")
        if name:
            out.append(name)
    return out


def _deep_get(data: dict[str, Any], key: str) -> Any:
    """Best-effort nested getter for heterogeneous Scopus XML/JSON shapes."""
    for part in key.split("."):
        if not isinstance(data, dict):
            return None
        data = data.get(part)
    return data
