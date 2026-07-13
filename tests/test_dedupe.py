"""Unit tests for DOI normalization + source-precedence merge (pure functions)."""

from __future__ import annotations

import pytest

from literature_digest.models import Article
from literature_digest.sources.dedupe import Deduper, normalize_doi


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.1234/ABC", "10.1234/abc"),
        ("https://doi.org/10.1234/abc", "10.1234/abc"),
        ("http://dx.doi.org/10.1234/abc", "10.1234/abc"),
        ("doi:10.1234/abc", "10.1234/abc"),
        ("  10.1234/abc.  ", "10.1234/abc"),
        ("10.1234/abc).", "10.1234/abc"),
        (None, None),
        ("   ", None),
    ],
)
def test_normalize_doi(raw: str | None, expected: str | None) -> None:
    assert normalize_doi(raw) == expected


def test_dedupe_merges_by_normalized_doi_with_precedence() -> None:
    # Same paper from two sources, different DOI formatting + complementary fields.
    crossref = Article(
        doi="https://doi.org/10.1/X",
        title="Crossref title",
        journal="J. Cross",
        sources=["crossref"],
    )
    openalex = Article(
        doi="10.1/x",
        title="OpenAlex title",
        abstract="A reconstructed abstract.",
        year=2024,
        sources=["openalex"],
    )

    merged = Deduper().dedupe([crossref, openalex])

    assert len(merged) == 1
    art = merged[0]
    assert art.doi == "10.1/x"
    # openalex outranks crossref -> its title wins.
    assert art.title == "OpenAlex title"
    # abstract only exists on openalex; journal only on crossref -> both kept.
    assert art.abstract == "A reconstructed abstract."
    assert art.journal == "J. Cross"
    assert art.year == 2024
    # Provenance combined in precedence order.
    assert art.sources == ["openalex", "crossref"]


def test_dedupe_keeps_doiless_articles_and_order() -> None:
    a = Article(doi="10.1/a", title="A", sources=["openalex"])
    b = Article(doi=None, title="No DOI", sources=["crossref"])
    c = Article(doi="10.1/A", title="A dup", sources=["crossref"])

    out = Deduper().dedupe([a, b, c])

    # a and c merge into one; b passes through. First-appearance order preserved.
    assert [x.title for x in out] == ["A", "No DOI"]
    assert out[0].sources == ["openalex", "crossref"]
    assert out[1].doi is None


def test_dedupe_unions_matched_terms() -> None:
    game_model = Article(
        doi="10.1/x",
        title="Paper X",
        sources=["scopus"],
        matched_terms=["game_model"],
    )
    tracking_data = Article(
        doi="10.1/X",
        title="Paper X",
        sources=["openalex"],
        matched_terms=["tracking_data"],
    )

    out = Deduper().dedupe([game_model, tracking_data])

    assert len(out) == 1
    assert out[0].matched_terms == ["game_model", "tracking_data"]
