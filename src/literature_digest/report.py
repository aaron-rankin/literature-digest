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


@dataclass
class AreaIndexRow:
    """One row of the index page summarizing an area's latest run."""

    slug: str
    name: str
    last_run: datetime | None
    article_count: int
    threshold: int


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
    ) -> Path:
        """Render one area's HTML report. Returns the path written.

        Articles are sorted by screening score descending (unscored last).
        """
        sorted_articles = sorted(
            articles,
            key=lambda a: a.screening.score if a.screening else -1,
            reverse=True,
        )
        template = self.env.get_template("area.html.j2")
        html = template.render(
            area=area,
            articles=sorted_articles,
            threshold=threshold,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        out = self.output_dir / "areas" / f"{area.slug}.html"
        out.write_text(html, encoding="utf-8")
        return out
