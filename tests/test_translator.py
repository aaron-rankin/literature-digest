"""Tests for Scopus-subset query translation and date-window computation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from literature_digest.query import (
    DateWindow,
    QueryTranslator,
    SourceQuery,
    compute_date_window,
    parse,
)


@pytest.fixture
def translator() -> QueryTranslator:
    return QueryTranslator()


def _sq(raw: str, name: str = "term") -> SourceQuery:
    return SourceQuery(term_name=name, parsed=parse(raw, term_name=name), area_slug="data_science")


# ── Scopus round-trip ───────────────────────────────────────────────────────
def test_scopus_round_trip_basic(translator: QueryTranslator) -> None:
    sq = _sq('TITLE-ABS-KEY("game model")')
    query = translator.to_scopus(sq, DateWindow())
    assert query == 'TITLE-ABS-KEY("game model")'


def test_scopus_round_trip_boolean_tree(translator: QueryTranslator) -> None:
    sq = _sq(
        'TITLE-ABS-KEY("game model") AND (TITLE-ABS-KEY("football") OR TITLE-ABS-KEY("soccer"))'
    )
    query = translator.to_scopus(sq, DateWindow())
    assert 'TITLE-ABS-KEY("game model")' in query
    assert "OR" in query
    assert "AND" in query


def test_scopus_injects_crawl_window_and_pubyear(translator: QueryTranslator) -> None:
    sq = _sq('TITLE-ABS-KEY("game model") AND PUBYEAR AFT 2024')
    window = DateWindow(
        crawl_from=datetime(2024, 1, 1, tzinfo=UTC),
        crawl_to=datetime(2024, 12, 31, tzinfo=UTC),
    )
    query = translator.to_scopus(sq, window)
    assert "ORIG-LOAD-DATE AFT 20240101" in query
    assert "ORIG-LOAD-DATE BEF 20241231" in query
    assert "PUBYEAR AFT 2024" in query


def test_scopus_pubyear_bounds_are_canonical(translator: QueryTranslator) -> None:
    sq = _sq("TITLE-ABS-KEY(a) AND PUBYEAR > 2023 AND PUBYEAR < 2027")
    query = translator.to_scopus(sq, DateWindow())
    assert "PUBYEAR AFT 2024" in query  # >2023 == >=2024 == AFT 2024
    assert "PUBYEAR < 2027" in query  # <2027 == <=2026


# ── OpenAlex ────────────────────────────────────────────────────────────────
def test_openalex_renders_tree_and_crawl_window(translator: QueryTranslator) -> None:
    sq = _sq(
        'TITLE-ABS-KEY("game model") AND (TITLE-ABS-KEY("football") OR TITLE-ABS-KEY("soccer"))'
    )
    window = DateWindow(
        crawl_from=datetime(2024, 1, 1, tzinfo=UTC),
        crawl_to=datetime(2024, 12, 31, tzinfo=UTC),
        pub_from=datetime(2024, 1, 1, tzinfo=UTC),
        pub_to=datetime(2024, 12, 31, tzinfo=UTC),
    )
    params = translator.to_openalex(sq, window)
    assert '"game model"' in params["search"]
    assert '"football"' in params["search"]
    assert '"soccer"' in params["search"]
    assert "from_created_date:2024-01-01" in params["filter"]
    assert "to_created_date:2024-12-31" in params["filter"]
    assert "from_publication_date:2024-01-01" in params["filter"]
    assert "to_publication_date:2024-12-31" in params["filter"]


def test_openalex_collapses_field_operators(translator: QueryTranslator) -> None:
    sq = _sq('TITLE-ABS-KEY-AUTH("author name")')
    params = translator.to_openalex(sq, DateWindow())
    assert params["search"] == '"author name"'


# ── Crossref ────────────────────────────────────────────────────────────────
def test_crossref_free_text_and_dates(translator: QueryTranslator) -> None:
    sq = _sq(
        'TITLE-ABS-KEY("game model") AND (TITLE-ABS-KEY("football") OR TITLE-ABS-KEY("soccer"))'
    )
    window = DateWindow(
        crawl_from=datetime(2024, 1, 1, tzinfo=UTC),
        crawl_to=datetime(2024, 12, 31, tzinfo=UTC),
        pub_from=datetime(2024, 1, 1, tzinfo=UTC),
        pub_to=datetime(2024, 12, 31, tzinfo=UTC),
    )
    params = translator.to_crossref(sq, window)
    assert params["query"] == "game model football soccer"
    assert "from-index-date:2024-01-01" in params["filter"]
    assert "until-index-date:2024-12-31" in params["filter"]
    assert "from-pub-date:2024-01-01" in params["filter"]
    assert "until-pub-date:2024-12-31" in params["filter"]


# ── Date window computation ─────────────────────────────────────────────────
def test_date_window_first_run_uses_first_run_lookback() -> None:
    now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
    window = compute_date_window(
        last_run=None,
        lookback_days=17,
        first_run_lookback_days=90,
        pubyear_from=2024,
        pubyear_to=2026,
        now=now,
    )
    assert window.crawl_from == now - timedelta(days=90)
    assert window.crawl_to == now
    assert window.pub_from == datetime(2024, 1, 1, tzinfo=UTC)
    assert window.pub_to == datetime(2026, 12, 31, tzinfo=UTC)


def test_date_window_subsequent_run_uses_lookback() -> None:
    now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
    last_run = datetime(2024, 6, 10, 12, 0, 0, tzinfo=UTC)
    window = compute_date_window(
        last_run=last_run,
        lookback_days=17,
        first_run_lookback_days=90,
        pubyear_from=None,
        pubyear_to=None,
        now=now,
    )
    assert window.crawl_from == last_run - timedelta(days=17)
    assert window.crawl_to == now
    assert window.pub_from is None
    assert window.pub_to is None
