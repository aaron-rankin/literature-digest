"""Jinja2 report renderer: index page + one HTML file per research area.

Writes to `<data_dir>/reports/index.html` and `<data_dir>/reports/areas/<slug>.html`.
The reports tree is created on demand. This module is fully implemented in
Phase 1 because rendering is stable infrastructure with no external APIs to mock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from literature_digest.config import AreaConfig
from literature_digest.models import Article

# Half-width of the borderline band (D9). Articles scoring within threshold ±N
# are flagged "borderline" in the report so a human can double-check them.
DEFAULT_BORDERLINE_BAND = 5


@dataclass
class AreaIndexRow:
    """One row of the index page summarizing an area's latest run."""

    slug: str
    name: str
    last_run: datetime | None
    article_count: int
    threshold: int


@dataclass
class TermMeta:
    """One search term exposed as a filter button in the area report."""

    name: str
    count: int


def _sort_key(a: Article) -> tuple[int, int]:
    """Sort scored articles first by score descending; unscored articles last."""
    score = a.screening.score if a.screening else -1
    return (0 if a.screening else 1, -score)


def build_filterable_articles(
    articles: list[Article],
) -> tuple[list[Article], list[TermMeta]]:
    """Deduplicate, sort, and index articles for the flat filtered report.

    Each article appears exactly once in the returned list, sorted by screening
    score descending globally (unscored articles sort last). The companion
    ``TermMeta`` list enumerates every distinct matched search term in
    first-seen order of ``Article.matched_terms``, plus an ``"Other"`` entry
    when any untagged articles are present. A multi-term article counts toward
    *each* matching term's count (so the sum of per-term counts can exceed the
    unique total) — this matches the per-term duplication the filter reproduces.
    """
    order: list[str] = []
    counts: dict[str, int] = {}
    has_other = False

    for art in articles:
        terms = art.matched_terms
        if not terms:
            has_other = True
            continue
        for term in terms:
            if term not in counts:
                counts[term] = 0
                order.append(term)
            counts[term] += 1

    sorted_articles = sorted(articles, key=_sort_key)

    terms_meta = [TermMeta(name=name, count=counts[name]) for name in order]
    if has_other:
        terms_meta.append(
            TermMeta(
                name="Other",
                count=sum(1 for a in articles if not a.matched_terms),
            )
        )
    return sorted_articles, terms_meta


class ReportRenderer:
    """Renders the per-area HTML reports and the index page."""

    def __init__(self, templates_dir: Path, output_dir: Path) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "html.j2"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.output_dir = output_dir
        (output_dir / "areas").mkdir(parents=True, exist_ok=True)

    def render_index(self, rows: list[AreaIndexRow]) -> Path:
        """Render the top-level index page. Returns the path written."""
        template = self.env.get_template("index.html.j2")
        html = template.render(areas=rows, generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"))
        out = self.output_dir / "index.html"
        out.write_text(html, encoding="utf-8")
        return out

    def render_area(
        self,
        area: AreaConfig,
        articles: list[Article],
        threshold: int,
        borderline_band: int = DEFAULT_BORDERLINE_BAND,
    ) -> Path:
        """Render one area's HTML report. Returns the path written.

        Articles are deduplicated into a single flat list sorted by score
        descending globally (unscored last). Each matched search term becomes a
        filter button along the top of the report. Articles whose score falls
        within ``threshold ± borderline_band`` are flagged "borderline" so the
        template can mark them (D9).
        """
        sorted_articles, terms = build_filterable_articles(articles)
        template = self.env.get_template("area.html.j2")
        html = template.render(
            area=area,
            articles=sorted_articles,
            terms=terms,
            threshold=threshold,
            borderline_band=borderline_band,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        out = self.output_dir / "areas" / f"{area.slug}.html"
        out.write_text(html, encoding="utf-8")
        return out
