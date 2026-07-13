"""Tests for the report renderer and templates.

Structure assertions cover the key elements of the deduplicated area report
(filter buttons, one card per unique article, data-terms attributes, term pills,
borderline flag, key-takeaway element, copy button, filter JS) plus
representative fragment snapshots of a filter button and an article card.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from literature_digest.config import AreaConfig
from literature_digest.models import ActionPoint, Article, ScreeningResult
from literature_digest.report import AreaIndexRow, ReportRenderer, build_filterable_articles

REPO_TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def _area(
    slug: str = "data_science", name: str = "Data Science", threshold: int = 60
) -> AreaConfig:
    return AreaConfig(slug=slug, name=name, threshold=threshold, enabled=True)


def _sample_articles() -> list[Article]:
    return [
        Article(
            doi="10.9999/strong",
            title="Strong paper on game models",
            abstract="A long abstract that we keep collapsed by default.",
            authors=["Smith, J.", "Lee, K."],
            journal="J Sports Sci",
            year=2025,
            matched_terms=["game_model", "style_of_play"],
            screening=ScreeningResult(
                score=88,
                category="directly actionable",
                rationale="Applies directly to weekly opposition prep.",
                key_takeaway="Use the positional compactness index in opposition reports.",
            ),
            action_points=[
                ActionPoint(
                    text="Adopt the compactness index for opposition dossiers.",
                    category="directly actionable",
                ),
            ],
        ),
        Article(
            doi="10.9999/moderate",
            title="Moderate monitoring paper",
            abstract="An abstract about athlete tracking workloads.",
            authors=["Doe, A."],
            year=2024,
            matched_terms=["tracking_data"],
            screening=ScreeningResult(
                score=64,
                category="monitoring",
                rationale="Worth tracking but not yet ready to adopt.",
            ),
        ),
        Article(
            doi="10.9999/borderline",
            title="Borderline paper just above threshold",
            abstract="An edge-case abstract.",
            authors=["Roe, R."],
            year=2024,
            matched_terms=["tracking_data"],
            screening=ScreeningResult(
                score=61,
                category="monitoring",
                rationale="Near the threshold; needs human review.",
            ),
        ),
        Article(
            doi=None,
            title="Unscored legacy article",
            abstract=None,
            authors=["Anon"],
            year=2023,
            matched_terms=[],
        ),
    ]


@pytest.fixture()
def renderer(tmp_path: Path) -> ReportRenderer:
    return ReportRenderer(templates_dir=REPO_TEMPLATES, output_dir=tmp_path / "reports")


# ── build_filterable_articles ────────────────────────────────────────────────


def test_build_filterable_articles_sorts_globally_by_score() -> None:
    sorted_articles, _terms = build_filterable_articles(_sample_articles())
    scores = [a.screening.score for a in sorted_articles if a.screening]
    assert scores == sorted(scores, reverse=True)
    # Unscored articles sort last.
    assert sorted_articles[-1].screening is None


def test_build_filterable_articles_term_counts_dedup_multi_term() -> None:
    _sorted, terms = build_filterable_articles(_sample_articles())
    by_name = {t.name: t.count for t in terms}
    # Terms in first-seen order: game_model, style_of_play, tracking_data, Other.
    assert [t.name for t in terms] == ["game_model", "style_of_play", "tracking_data", "Other"]
    # The multi-term (strong) article counts toward both game_model and style_of_play.
    assert by_name["game_model"] == 1
    assert by_name["style_of_play"] == 1
    # tracking_data holds the moderate + borderline articles.
    assert by_name["tracking_data"] == 2
    # Untagged article falls under Other.
    assert by_name["Other"] == 1


def test_build_filterable_articles_returns_unique_articles() -> None:
    sorted_articles, _terms = build_filterable_articles(_sample_articles())
    dois = [a.doi for a in sorted_articles]
    # No duplicates even though the strong article matches two terms.
    assert len(dois) == len(set(dois)) == 4


# ── render_area structure ────────────────────────────────────────────────────


def _area_html(renderer: ReportRenderer) -> str:
    out = renderer.render_area(_area(), _sample_articles(), threshold=60, borderline_band=5)
    return out.read_text(encoding="utf-8")


def test_area_report_renders_one_card_per_unique_article(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    # 4 unique articles -> 4 cards (no duplication of the multi-term article).
    assert html.count('<article class="card') == 4


def test_area_report_has_filter_button_per_term_plus_all(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    # "All" + one button per term (game_model, style_of_play, tracking_data, Other).
    assert html.count('class="filter-btn"') == 5
    assert 'data-term="all"' in html
    for term in ("game_model", "style_of_play", "tracking_data", "Other"):
        assert f'data-term="{term}"' in html


def test_area_report_card_carries_data_terms_attribute(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    # The multi-term (strong) card carries every matched term as a token.
    assert 'data-terms="game_model style_of_play"' in html
    # The untagged card is tagged with the synthetic "other" token.
    assert 'data-terms="other"' in html


def test_area_report_term_pills_no_current_distinction(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    # No "current" pill class or "also:" prefix — all matched-term pills are equal.
    assert "pill current" not in html
    assert "also:" not in html
    # The multi-term card shows one pill per matched term.
    assert html.count(">game_model<") + html.count(">game_model ") >= 1
    assert html.count(">style_of_play<") + html.count(">style_of_play ") >= 1
    # Untagged card shows a single Other pill.
    assert 'class="pill other">Other<' in html


def test_area_report_has_filter_script_and_hash_handler(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    # The inline filter script reads/writes the URL hash and toggles card visibility.
    assert "termFromHash" in html
    assert "hashchange" in html
    assert "applyFilter" in html
    # Empty-filter placeholder exists for filters that match zero cards.
    assert 'id="empty-filter"' in html


def test_area_report_flags_borderline_articles(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    # 64 and 61 fall within threshold(60) ± 5 -> borderline (one card each now).
    assert html.count("flag-borderline") >= 2
    assert html.count("is-borderline") >= 2


def test_area_report_includes_key_takeaway_element(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    # The strong card has a key_takeaway and renders it once (no duplication).
    assert "Use the positional compactness index in opposition reports." in html
    assert html.count('class="takeaway"') == 1


def test_area_report_falls_back_to_first_action_point_for_takeaway(
    renderer: ReportRenderer,
) -> None:
    art = Article(
        doi="10.9999/kt-fallback",
        title="Fallback takeaway paper",
        abstract="abstract",
        authors=["X"],
        year=2025,
        matched_terms=["game_model"],
        screening=ScreeningResult(score=85, category="directly actionable", rationale="Because."),
        action_points=[
            ActionPoint(
                text="Adopt the fallback action point wording.", category="directly actionable"
            )
        ],
    )
    out = renderer.render_area(_area(), [art], threshold=60, borderline_band=5)
    html = out.read_text(encoding="utf-8")
    assert "Adopt the fallback action point wording." in html


def test_area_report_has_copy_citation_button(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    assert html.count('class="btn-copy"') == 4  # one per unique card
    # The strong article's DOI link appears once (not duplicated per term).
    assert "https://doi.org/10.9999/strong" in html


def test_area_report_has_print_stylesheet(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    assert "@media print" in html
    assert "details.abstract > .abstract-body" in html
    # Filter buttons are hidden in print; hidden cards are forced visible.
    assert ".filters" in html
    assert 'article.card[hidden]' in html


def test_area_report_abstract_is_collapsible(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    assert html.count('<details class="abstract">') >= 3  # at least the scored articles


def test_area_report_category_chips_use_text_weight_not_icons(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    assert html.count("chip directly-actionable") >= 1
    assert html.count("chip monitoring") >= 1
    # No icons / emoji in chips by design.
    assert "icon" not in html.lower()


# ── Snapshot: representative card + filter bar fragments ────────────────────


def test_snapshot_strong_article_card_fragment(renderer: ReportRenderer) -> None:
    """Lock the structure of a representative strong band + actionable card."""
    html = _area_html(renderer)
    start = html.find('<article class="card band-strong')
    assert start != -1, "expected a strong-band card in the report"
    end = html.find("</article>", start) + len("</article>")
    card = html[start:end]
    snapshot = (
        '<article class="card band-strong" data-terms="game_model style_of_play">\n'
        '        <div class="card-top">\n'
        '          <div class="badges">\n'
        '              <span class="score band-strong">88</span>\n'
        '              <span class="chip directly-actionable">directly actionable</span>\n'
    )
    # Prefix must match exactly so future styling refactors don't silently break the header.
    assert card.startswith(snapshot)


def test_snapshot_filter_bar_fragment(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    start = html.find('<div class="filters"')
    assert start != -1
    end = html.find("</div>", start) + len("</div>")
    bar = html[start:end]
    assert bar.startswith('<div class="filters"')
    # "All" button is first and pressed by default.
    assert 'data-term="all" aria-pressed="true"' in bar
    # Each term button carries its count.
    assert "game_model <span" in bar
    assert "tracking_data <span" in bar


# ── render_index stays functionally unchanged ────────────────────────────────


def test_index_page_keeps_table_and_shares_typography(renderer: ReportRenderer) -> None:
    rows = [
        AreaIndexRow(
            slug="data_science", name="Data Science", last_run=None, article_count=4, threshold=60
        )
    ]
    html = renderer.render_index(rows).read_text(encoding="utf-8")
    assert "<table>" in html
    assert "Data Science" in html
    # Shares the restyled CSS tokens.
    assert "--accent: #2563eb" in html


def test_index_page_last_run_formats_or_never(renderer: ReportRenderer) -> None:
    rows = [
        AreaIndexRow(
            slug="a", name="A", last_run=datetime(2026, 1, 2, 3, 4), article_count=1, threshold=60
        ),
    ]
    html = renderer.render_index(rows).read_text(encoding="utf-8")
    assert "never" not in html  # with a datetime present
