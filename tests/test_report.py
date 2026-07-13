"""Tests for the report renderer and templates.

Structure assertions cover the key elements of the restyled area report (term
headings, card count, borderline class, key-takeaway element, copy button) plus
a representative fragment snapshot of an article card and a term section.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from literature_digest.config import AreaConfig
from literature_digest.models import ActionPoint, Article, ScreeningResult
from literature_digest.report import AreaIndexRow, ReportRenderer, build_term_sections

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


# ── build_term_sections ───────────────────────────────────────────────────────


def test_build_term_sections_groups_by_matched_term() -> None:
    sections = build_term_sections(_sample_articles())
    names = [s.name for s in sections]
    # Distinct terms in first-seen order, with an "Other" bucket for untagged work.
    assert names == ["game_model", "style_of_play", "tracking_data", "Other"]


def test_build_term_sections_duplicates_under_each_term() -> None:
    sections = build_term_sections(_sample_articles())
    buckets = {s.name: s.articles for s in sections}
    # The strong article matches two terms and must appear under both.
    titles_game_model = {a.title for a in buckets["game_model"]}
    titles_style = {a.title for a in buckets["style_of_play"]}
    assert "Strong paper on game models" in titles_game_model
    assert "Strong paper on game models" in titles_style


def test_build_term_sections_sorts_by_score_descending_within_term() -> None:
    sections = build_term_sections(_sample_articles())
    tracking = next(s for s in sections if s.name == "tracking_data")
    scores = [a.screening.score for a in tracking.articles if a.screening]
    assert scores == sorted(scores, reverse=True)
    # No duplicate of the same article inside one term bucket.
    dois = [a.doi for a in tracking.articles]
    assert len(dois) == len(set(dois))


# ── render_area structure ────────────────────────────────────────────────────


def _area_html(renderer: ReportRenderer) -> str:
    out = renderer.render_area(_area(), _sample_articles(), threshold=60, borderline_band=5)
    return out.read_text(encoding="utf-8")


def test_area_report_has_term_section_headings(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    for name in ("game_model", "style_of_play", "tracking_data", "Other"):
        assert 'id="term-' in html or name in html  # section anchors exist
    assert html.count('<section class="term"') == 4


def test_area_report_renders_one_card_per_term_membership(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    # strong (2 terms) + moderate + borderline + untagged = 5 cards.
    assert html.count('<article class="card') == 5


def test_area_report_flags_borderline_articles(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    # 64 and 61 fall within threshold(60) ± 5 → borderline.
    # Each borderline card carries a flag span and a border-left borderline class.
    assert html.count("flag-borderline") >= 2  # spans only (CSS uses a separate selector name)
    assert html.count("is-borderline") >= 2  # card class


def test_area_report_includes_key_takeaway_element(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    # The strong card has a key_takeaway from the screening result and renders it.
    assert "Use the positional compactness index in opposition reports." in html
    assert html.count('class="takeaway"') == 2  # appears under both terms the article matches


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
    assert html.count('class="btn-copy"') == 5  # one per card
    # The strong article appears twice; each card carries the DOI link in data-citation.
    assert "https://doi.org/10.9999/strong" in html


def test_area_report_has_sticky_sidebar_and_mobile_term_chips(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    assert 'nav class="toc"' in html
    assert 'class="term-chips"' in html


def test_area_report_has_print_stylesheet(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    assert "@media print" in html
    assert "details.abstract > .abstract-body" in html


def test_area_report_abstract_is_collapsible(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    assert html.count('<details class="abstract">') >= 3  # at least the scored articles


def test_area_report_category_chips_use_text_weight_not_icons(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    assert html.count("chip directly-actionable") >= 1
    assert html.count("chip monitoring") >= 1
    # No icons / emoji in chips by design.
    assert "icon" not in html.lower()


# ── Snapshot: representative card + term section fragments ────────────────────


def test_snapshot_strong_article_card_fragment(renderer: ReportRenderer) -> None:
    """Lock the structure of a representative strong band + actionable card."""
    html = _area_html(renderer)
    start = html.find('<article class="card band-strong')
    assert start != -1, "expected a strong-band card in the report"
    end = html.find("</article>", start) + len("</article>")
    card = html[start:end]
    snapshot = (
        '<article class="card band-strong">\n'
        '          <div class="card-top">\n'
        '            <div class="badges">\n'
        '                <span class="score band-strong">88</span>\n'
        '                <span class="chip directly-actionable">directly actionable</span>\n'
    )
    # Prefix must match exactly so future styling refactors don't silently break the header.
    assert card.startswith(snapshot)


def test_snapshot_term_section_has_heading_and_anchor(renderer: ReportRenderer) -> None:
    html = _area_html(renderer)
    start = html.find('<section class="term" id="term-tracking-data">')
    assert start != -1
    end = html.find("</section>", start) + len("</section>")
    section = html[start:end]
    assert section.startswith('<section class="term" id="term-tracking-data">')
    assert "<h2>tracking_data</h2>" in section
    # tracking_data bucket holds the moderate and borderline cards (score desc).
    assert "Moderate monitoring paper" in section
    assert "Borderline paper just above threshold" in section


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
