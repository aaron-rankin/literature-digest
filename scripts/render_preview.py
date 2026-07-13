"""Render a preview area report from fixtures, with no LLM or network calls.

Use this while iterating on report UI / templates so you can see the output in
a browser without running the full pipeline (which calls the LLM and is slow /
hangs when no key is configured). It loads `data/fixtures/<area>/*.json`,
synthesizes deterministic ScreeningResults + ActionPoints so the cards show all
score bands / categories / borderline flags, and writes to `data/reports/`.

    uv run python scripts/render_preview.py --area data_science
    open data/reports/areas/data_science.html

Deterministic given the fixture contents (no randomness) so re-running
diff cleanly against the last render.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from literature_digest.config import AreaConfig, load_areas
from literature_digest.models import ActionPoint, Article, ScreeningResult
from literature_digest.report import AreaIndexRow, ReportRenderer

REPO_ROOT = Path(__file__).resolve().parent.parent
CATEGORIES = ["directly actionable", "monitoring", "background"]


def _hash_idx(text: str, mod: int) -> int:
    h = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") % mod


def _synth_screening(
    article: Article, threshold: int, borderline_band: int
) -> ScreeningResult | None:
    """Deterministic fake screening so the report exercises every score band."""
    if not article.title:
        return None
    # Spread of scores: 80-100 (strong), 60-79 (moderate), <60 (low/dropped).
    roll = _hash_idx(article.title + (article.doi or ""), 100)
    score = 40 + roll  # 40..139, clamp below
    if score > 100:
        score = 100 - (score % 20)
    # Half of moderate band is borderline (near threshold).
    cat_idx = _hash_idx(article.title + "cat", 3)
    category = CATEGORIES[cat_idx]
    rationale = (
        f"Synthesised preview screening for {article.title!r}. "
        f"This is a deterministic stand-in for the LLM call so the report UI "
        f"can be iterated on offline."
    )
    takeaway = f"Preview takeaway for {article.title[:60]}."
    return ScreeningResult(
        score=score,
        category=category,  # type: ignore[arg-type]
        rationale=rationale,
        key_takeaway=takeaway,
    )


def _synth_action_points(article: Article, category: str) -> list[ActionPoint]:
    return [
        ActionPoint(
            text=f"Review {article.title[:50]!r} and decide whether to adopt.",
            category=category,  # type: ignore[arg-type]
        )
    ]


def load_fixture_articles(area_slug: str) -> list[Article]:
    fixtures_dir = REPO_ROOT / "data" / "fixtures" / area_slug
    if not fixtures_dir.exists():
        return []
    articles: list[Article] = []
    for path in sorted(fixtures_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        for item in raw:
            articles.append(Article.model_validate(item))
    return articles


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", default="data_science", help="area slug")
    parser.add_argument("--threshold", type=int, default=None, help="override threshold")
    parser.add_argument("--borderline-band", type=int, default=5, help="±N around threshold")
    args = parser.parse_args()

    areas_file = load_areas(REPO_ROOT / "config" / "areas.yaml")
    area_cfg = next(
        (a for a in areas_file.areas if a.slug == args.area),
        AreaConfig(slug=args.area, name=args.area.replace("_", " ").title()),
    )
    threshold = args.threshold or areas_file.threshold_for(area_cfg)

    raw = load_fixture_articles(args.area)
    arts: list[Article] = []
    for art in raw:
        scr = _synth_screening(art, threshold, args.borderline_band)
        if scr and scr.score >= threshold:
            art.screening = scr
            art.action_points = _synth_action_points(art, scr.category)
            arts.append(art)
        elif scr:
            # Below threshold: still include a couple so "low" band renders.
            if _hash_idx(art.title or "", 3) == 0:
                art.screening = scr
                arts.append(art)

    templates = REPO_ROOT / "templates"
    out_dir = REPO_ROOT / "data" / "reports"
    renderer = ReportRenderer(templates_dir=templates, output_dir=out_dir)

    area_path = renderer.render_area(
        area_cfg, arts, threshold=threshold, borderline_band=args.borderline_band
    )
    index_path = renderer.render_index([
        AreaIndexRow(
            slug=area_cfg.slug,
            name=area_cfg.name,
            last_run=None,
            article_count=len(arts),
            threshold=threshold,
        )
    ])
    print(f"rendered {len(arts)} articles → {area_path}")
    print(f"index → {index_path}")
    print(f"open {area_path.as_uri()}")


if __name__ == "__main__":
    main()