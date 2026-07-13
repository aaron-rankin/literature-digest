"""respx-mocked tests for the Elsevier Scopus Search API source."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from literature_digest.config import Settings
from literature_digest.query import DateWindow, SourceQuery, parse
from literature_digest.sources.scopus_api import ScopusApiSource


@pytest.fixture
def settings() -> Settings:
    return Settings(scopus_api_key="test-key")


@pytest.fixture
def source_query() -> SourceQuery:
    raw = 'TITLE-ABS-KEY("game model") AND PUBYEAR AFT 2024'
    return SourceQuery(
        term_name="game_model",
        parsed=parse(raw, term_name="game_model"),
        area_slug="data_science",
    )


@pytest.fixture
def window() -> DateWindow:
    return DateWindow(
        crawl_from=datetime(2024, 1, 1, tzinfo=UTC),
        crawl_to=datetime(2024, 12, 31, tzinfo=UTC),
    )


def _search_entry() -> dict:
    return {
        "dc:title": "Game models in elite football",
        "dc:creator": "Smith, J.",
        "prism:publicationName": "J. Sports Sci.",
        "prism:coverDate": "2024-05-01",
        "prism:doi": "10.1/SCOPUS",
        "dc:description": "Abstract from search view.",
    }


def _search_response(entries: list[dict], total: int | None = None) -> dict:
    return {
        "search-results": {
            "opensearch:totalResults": str(total if total is not None else len(entries)),
            "entry": entries,
        }
    }


@respx.mock
def test_search_parses_entry(
    settings: Settings, source_query: SourceQuery, window: DateWindow
) -> None:
    respx.get("https://api.elsevier.com/content/search/scopus").mock(
        return_value=httpx.Response(200, json=_search_response([_search_entry()]))
    )

    articles = ScopusApiSource(settings).search(source_query, window)

    assert len(articles) == 1
    art = articles[0]
    assert art.doi == "10.1/scopus"
    assert art.title == "Game models in elite football"
    assert art.authors == ["Smith, J."]
    assert art.journal == "J. Sports Sci."
    assert art.year == 2024
    assert art.sources == ["scopus"]
    assert art.matched_terms == ["game_model"]


@respx.mock
def test_search_retries_429_then_succeeds(
    settings: Settings, source_query: SourceQuery, window: DateWindow
) -> None:
    route = respx.get("https://api.elsevier.com/content/search/scopus").mock(
        side_effect=[
            httpx.Response(429, json={"error": "too many requests"}),
            httpx.Response(200, json=_search_response([_search_entry()])),
        ]
    )

    articles = ScopusApiSource(settings).search(source_query, window)

    assert len(articles) == 1
    assert route.call_count == 2


@respx.mock
def test_search_429_exhausted_raises(
    settings: Settings, source_query: SourceQuery, window: DateWindow
) -> None:
    respx.get("https://api.elsevier.com/content/search/scopus").mock(
        return_value=httpx.Response(429, json={"error": "too many requests"})
    )

    with pytest.raises(Exception):  # noqa: B017
        ScopusApiSource(settings).search(source_query, window)


@respx.mock
def test_enrich_by_doi(settings: Settings) -> None:
    respx.get("https://api.elsevier.com/content/abstract/doi/10.1/scopus").mock(
        return_value=httpx.Response(
            200,
            json={
                "abstracts-retrieval-response": {
                    "coredata": {
                        "dc:title": "Enriched title",
                        "prism:publicationName": "Enriched Journal",
                        "prism:coverDate": "2024-08-15",
                        "prism:doi": "10.1/SCOPUS",
                        "dc:description": "Enriched abstract.",
                    }
                }
            },
        )
    )

    art = ScopusApiSource(settings).enrich("10.1/scopus")

    assert art is not None
    assert art.title == "Enriched title"
    assert art.abstract == "Enriched abstract."
    assert art.doi == "10.1/scopus"


@respx.mock
def test_search_backfills_abstract_from_abstract_api(
    settings: Settings, source_query: SourceQuery, window: DateWindow
) -> None:
    entry = _search_entry()
    entry.pop("dc:description")  # no abstract from search view

    respx.get("https://api.elsevier.com/content/search/scopus").mock(
        return_value=httpx.Response(200, json=_search_response([entry]))
    )
    respx.get("https://api.elsevier.com/content/abstract/doi/10.1/scopus").mock(
        return_value=httpx.Response(
            200,
            json={
                "abstracts-retrieval-response": {
                    "coredata": {
                        "dc:title": "Game models in elite football",
                        "prism:doi": "10.1/SCOPUS",
                        "dc:description": "Abstract from retrieval API.",
                    }
                }
            },
        )
    )

    articles = ScopusApiSource(settings).search(source_query, window)

    assert len(articles) == 1
    assert articles[0].abstract == "Abstract from retrieval API."
