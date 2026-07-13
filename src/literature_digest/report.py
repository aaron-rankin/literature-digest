"""Jinja2 report renderer: index page + one HTML file per research area.

Writes to `<data_dir>/reports/index.html` and `<data_dir>/reports/areas/<slug>.html`.
The reports tree is created on demand. This module is fully implemented in
Phase 1 because rendering is stable infrastructure with no external APIs to mock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
class TermSection:
    """One per-term group of articles in an area report."""

    name: str
    articles: list[Article] = field(default_factory=list)

    @property
    def slug(self) -> str:
        """Anchor-friendly slug for the term name."""
        return "".join(c if c.isalnum() else "-" for c in self.name.lower()).strip("-")

    @property
    def count(self) -> int:
        return len(self.articles)


def build_term_sections(articles: list[Article]) -> list[TermSection]:
    """Group articles by matched search term, sorted by score within each term.

    An article matched by multiple terms appears once under each matching term
    (D7 / Q3). Each term's articles are sorted by screening score descending;
    unscored articles sort last. Terms are returned in first-seen order of
    `Article.matched_terms`, with any articles that have no matched terms
    collected under a single "Other" section at the end.
    """
    order: list[str] = []
    buckets: dict[str, list[Article]] = {}
    untagged: list[Article] = []

    for art in articles:
        terms = art.matched_terms
        if not terms:
            untagged.append(art)
            continue
        for term in terms:
            if term not in buckets:
                buckets[term] = []
                order.append(term)
            # Avoid duplicating the same article inside one term bucket.
            if art not in buckets[term]:
                buckets[term].append(art)

    def _sort_key(a: Article) -> tuple[int, int]:
        score = a.screening.score if a.screening else -1
        return (1 if a.screening else 0, -score)

    sections = [
        TermSection(name=name, articles=sorted(buckets[name], key=_sort_key)) for name in order
    ]
    if untagged:
        sections.append(TermSection(name="Other", articles=sorted(untagged, key=_sort_key)))
    return sections


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

        Articles are grouped by search term (D7), sorted by score descending
        within each term. Articles whose score falls within ``threshold ±
        borderline_band`` are flagged "borderline" so the template can mark
        them (D9).
        """
        sections = build_term_sections(articles)
        template = self.env.get_template("area.html.j2")
        html = template.render(
            area=area,
            articles=articles,
            sections=sections,
            threshold=threshold,
            borderline_band=borderline_band,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        out = self.output_dir / "areas" / f"{area.slug}.html"
        out.write_text(html, encoding="utf-8")
        return out
