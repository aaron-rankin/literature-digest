"""respx-mocked tests for the free-API ingestion sources (OpenAlex + Crossref)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import httpx
import pytest
import respx

from literature_digest.config import AreaConfig, LoadedArea, SearchTerm, Settings
from literature_digest.query import DateWindow, SourceQuery, parse
from literature_digest.sources.crossref import CrossrefSource
from literature_digest.sources.openalex import OpenAlexSource


@pytest.fixture
def settings() -> Settings:
    return Settings(contact_email="tester@example.org")


@pytest.fixture
def area() -> LoadedArea:
    raw = 'TITLE-ABS-KEY("sports nutrition") OR TITLE-ABS-KEY("ergogenic aid")'
    return LoadedArea(
        config=AreaConfig(
            slug="sports-nutrition",
            name="Sports Nutrition",
            threshold=50,
        ),
        terms=[
            SearchTerm(
                name="sports-nutrition",
                raw_query=raw,
                path=Path("/tmp/sports-nutrition.txt"),
                parsed=parse(raw, term_name="sports-nutrition"),
            ),
        ],
    )


@pytest.fixture
def source_query(area: LoadedArea) -> SourceQuery:
    return SourceQuery(
        term_name=area.terms[0].name,
        parsed=area.terms[0].parsed,
        area_slug=area.slug,
    )


@pytest.fixture
def window() -> DateWindow:
    return DateWindow(
        crawl_from=datetime(2024, 1, 1),
        crawl_to=datetime(2024, 12, 31),
    )


# ── OpenAlex ────────────────────────────────────────────────────────────────
def _oa_work() -> dict:
    return {
        "id": "https://openalex.org/W1",
        "doi": "https://doi.org/10.1/OA",
        "display_name": "Fueling for endurance",
        "publication_year": 2024,
        "publication_date": "2024-03-15",
        "abstract_inverted_index": {"Carbs": [0], "matter": [1, 3], "really": [2]},
        "authorships": [
            {"author": {"display_name": "Ada Lovelace"}},
            {"author": {"display_name": "Alan Turing"}},
        ],
        "primary_location": {
            "source": {"display_name": "J. Sports Nutrition"},
            "landing_page_url": "https://example.org/oa",
        },
    }


@respx.mock
def test_openalex_search_parses_and_reconstructs_abstract(
    settings: Settings, source_query: SourceQuery, window: DateWindow
) -> None:
    route = respx.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(
            200, json={"results": [_oa_work()], "meta": {"next_cursor": None}}
        )
    )

    articles = OpenAlexSource(settings).search(source_query, window)

    assert len(articles) == 1
    art = articles[0]
    assert art.doi == "10.1/oa"
    assert art.title == "Fueling for endurance"
    assert art.abstract == "Carbs matter really matter"
    assert art.authors == ["Ada Lovelace", "Alan Turing"]
    assert art.journal == "J. Sports Nutrition"
    assert art.year == 2024
    assert art.pub_date == datetime(2024, 3, 15)
    assert art.sources == ["openalex"]
    assert art.matched_terms == [source_query.term_name]

    # Polite pool + crawl window went out on the request.
    request = route.calls.last.request
    assert "mailto=tester%40example.org" in str(request.url)
    assert "from_created_date%3A2024-01-01" in str(request.url)
    assert "to_created_date%3A2024-12-31" in str(request.url)


def _oa_work2() -> dict:
    work = _oa_work()
    work["id"] = "https://openalex.org/W2"
    work["doi"] = "https://doi.org/10.1/OA2"
    work["display_name"] = "Second page work"
    return work


@respx.mock
def test_openalex_search_follows_cursor_pagination(
    settings: Settings, source_query: SourceQuery
) -> None:
    page1 = {"results": [_oa_work()], "meta": {"next_cursor": "CURSOR2"}}
    page2 = {"results": [_oa_work2()], "meta": {"next_cursor": None}}
    respx.get("https://api.openalex.org/works").mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    )

    articles = OpenAlexSource(settings).search(source_query, DateWindow())

    assert len(articles) == 2
    assert {a.doi for a in articles} == {"10.1/oa", "10.1/oa2"}


@respx.mock
def test_openalex_enrich_returns_none_on_404(settings: Settings) -> None:
    respx.get(url__startswith="https://api.openalex.org/works/").mock(
        return_value=httpx.Response(404)
    )
    assert OpenAlexSource(settings).enrich("10.1/missing") is None


# ── Crossref ────────────────────────────────────────────────────────────────
def _cr_item() -> dict:
    return {
        "DOI": "10.1/CR",
        "title": ["Cold water immersion and recovery"],
        "abstract": "<jats:p>Ice <jats:italic>helps</jats:italic> recovery.</jats:p>",
        "author": [{"given": "Grace", "family": "Hopper"}, {"family": "Dijkstra"}],
        "container-title": ["Journal of Recovery"],
        "issued": {"date-parts": [[2023, 6, 1]]},
        "URL": "https://doi.org/10.1/cr",
    }


@respx.mock
def test_crossref_search_parses_and_strips_jats(
    settings: Settings, source_query: SourceQuery, window: DateWindow
) -> None:
    route = respx.get("https://api.crossref.org/works").mock(
        return_value=httpx.Response(
            200, json={"message": {"items": [_cr_item()], "next-cursor": None}}
        )
    )

    articles = CrossrefSource(settings).search(source_query, window)

    assert len(articles) == 1
    art = articles[0]
    assert art.doi == "10.1/cr"
    assert art.title == "Cold water immersion and recovery"
    assert art.abstract == "Ice helps recovery."
    assert art.authors == ["Grace Hopper", "Dijkstra"]
    assert art.journal == "Journal of Recovery"
    assert art.year == 2023
    assert art.pub_date == datetime(2023, 6, 1)
    assert art.sources == ["crossref"]
    assert art.matched_terms == [source_query.term_name]

    request = route.calls.last.request
    assert "mailto=tester%40example.org" in str(request.url)
    assert "from-index-date%3A2024-01-01" in str(request.url)
    assert "until-index-date%3A2024-12-31" in str(request.url)
    assert "literature-digest" in request.headers["user-agent"]


@respx.mock
def test_crossref_search_follows_cursor_pagination(
    settings: Settings, source_query: SourceQuery
) -> None:
    page1 = {"message": {"items": [_cr_item()], "next-cursor": "AoJ..."}}
    page2 = {"message": {"items": [], "next-cursor": "AoJ..."}}
    respx.get("https://api.crossref.org/works").mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    )

    articles = CrossrefSource(settings).search(source_query, DateWindow())

    # Second page is empty -> loop stops; only page-1 item returned.
    assert len(articles) == 1
