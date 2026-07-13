"""Generate fake sample papers for offline `run --local` play.

Reads the search-term names for an area from `data/search_terms/<area>/*.txt`
(one term per file stem) and writes N fake `Article`-shaped papers per term to
`data/fixtures/<area>/<term>.json`.

The papers are entirely fictional (fake DOIs under the reserved 10.9999 prefix,
made-up authors/journals) but are shaped to exercise LLM screening: each term
gets a mix of "applied" (should score high), "method" (mid), and "tangential"
(should be dropped) papers so the threshold has something to discriminate.

Deterministic given `--seed`. Run with uv:

    uv run python scripts/generate_fixtures.py --area data_science --count 5
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

# Per-search-term vocabulary so titles/abstracts read on-topic.
TERM_THEMES: dict[str, dict[str, list[str]]] = {
    "game_model": {
        "concept": [
            "team game model",
            "tactical principles",
            "positional play framework",
            "playing-model adherence",
            "structured possession model",
        ],
        "metric": [
            "expected threat",
            "possession-chain value",
            "build-up progression rate",
            "positional compactness index",
        ],
    },
    "tracking_data": {
        "concept": [
            "optical tracking data",
            "GPS-derived positional data",
            "player tracking streams",
            "multi-camera tracking",
            "broadcast tracking",
        ],
        "metric": [
            "pitch-control surface",
            "off-ball run detection",
            "synchronised movement",
            "high-speed running distance",
        ],
    },
    "style_of_play": {
        "concept": [
            "style of play",
            "playing-style fingerprint",
            "team behavioural signature",
            "tactical identity",
            "possession vs direct style",
        ],
        "metric": [
            "passing network centrality",
            "vertical progression ratio",
            "pressing intensity (PPDA)",
            "field-tilt share",
        ],
    },
    "spatiotemporal": {
        "concept": [
            "spatiotemporal patterns",
            "spatiotemporal pitch occupation",
            "space-time interaction",
            "collective movement dynamics",
            "spatiotemporal pressing traps",
        ],
        "metric": [
            "Voronoi space control",
            "temporal synchronisation index",
            "space-generation rate",
            "convex-hull surface area",
        ],
    },
}

# Fallback theme for any term without a bespoke vocabulary above.
DEFAULT_THEME = {
    "concept": ["football analytics model", "match-analysis framework"],
    "metric": ["performance index", "team-behaviour metric"],
}

FIRST = [
    "Alvarien",
    "Boskovic",
    "Chidera",
    "Dufresne",
    "Enomoto",
    "Farkas",
    "GrØnvold",
    "Haddad",
    "Ishikawa",
    "Jovanetti",
    "Kristensen",
    "Laoutaris",
]
LAST = [
    "Mbeki",
    "Novak",
    "Oyelaran",
    "Petrov",
    "Quintero",
    "Rasmussen",
    "Sundqvist",
    "Tanaka",
    "Ubeda",
    "Virtanen",
    "Wojcik",
    "Xu",
]
JOURNALS = [
    "Journal of Sports Analytics",
    "International Journal of Performance Analysis in Sport",
    "Journal of Sports Sciences",
    "Frontiers in Sports Modelling",
    "European Journal of Sport Science",
]

# (tier, title_template, abstract_template). Tier only shapes the text so
# screening has a spread of relevance — it is not stored on the article.
TEMPLATES = [
    (
        "applied",
        "Validating {concept} against match outcomes in elite football",
        "We analysed a full competitive season of first-team matches to test whether "
        "{concept} derived from {metric} predicts match outcomes. Using data from an "
        "elite men's league, the model explained a meaningful share of variance in "
        "goal difference and was robust across opponents. The approach is directly "
        "usable by performance analysts to prepare opposition reports within the "
        "weekly training cycle.",
    ),
    (
        "applied",
        "A practitioner workflow for {concept} using {metric}",
        "This applied study describes and evaluates a workflow that turns raw {metric} "
        "into coach-facing {concept} summaries for an elite academy-to-first-team "
        "pathway. Across 30 matches the outputs agreed with expert coach ratings and "
        "shortened analysis turnaround, supporting adoption in a professional setting.",
    ),
    (
        "method",
        "A graph-neural approach to modelling {concept} from {metric}",
        "We propose a graph-neural architecture that learns {concept} representations "
        "from {metric}. On a benchmark of simulated possessions the method improves "
        "reconstruction error over baselines. Translation to applied decision-making "
        "is not evaluated here and would require validation in a live performance "
        "environment.",
    ),
    (
        "method",
        "Sensitivity of {concept} estimates to {metric} sampling frequency",
        "This methodological paper quantifies how {concept} estimates vary with the "
        "sampling frequency of {metric}. We report substantial bias below 10 Hz. The "
        "work is primarily technical and does not test performance outcomes, but "
        "informs data-quality requirements for analytics pipelines.",
    ),
    (
        "tangential",
        "{concept} in recreational five-a-side players: an exploratory study",
        "We explored {concept} using {metric} in a sample of recreational five-a-side "
        "players. Given the non-elite population, small pitch, and absence of a "
        "performance intervention, the findings are contextual only and unlikely to "
        "transfer to professional match preparation.",
    ),
]


def _authors(rng: random.Random) -> list[str]:
    n = rng.randint(2, 4)
    return [f"{rng.choice(LAST)}, {rng.choice(FIRST)[0]}." for _ in range(n)]


def _term_names(search_terms_dir: Path, area: str) -> list[str]:
    area_dir = search_terms_dir / area
    return sorted(p.stem for p in area_dir.glob("*.txt"))


def generate(area: str, count: int, seed: int, search_terms_dir: Path, fixtures_dir: Path) -> None:
    rng = random.Random(seed)
    terms = _term_names(search_terms_dir, area)
    if not terms:
        raise SystemExit(f"No search terms found under {search_terms_dir / area}/")

    out_dir = fixtures_dir / area
    out_dir.mkdir(parents=True, exist_ok=True)

    for term in terms:
        theme = TERM_THEMES.get(term, DEFAULT_THEME)
        papers = []
        for i in range(count):
            tier, title_t, abstract_t = TEMPLATES[i % len(TEMPLATES)]
            concept = rng.choice(theme["concept"])
            metric = rng.choice(theme["metric"])
            year = rng.choice([2024, 2025])
            papers.append(
                {
                    "doi": f"10.9999/fake.{area}.{term}.{i + 1}",
                    "title": title_t.format(concept=concept, metric=metric),
                    "abstract": abstract_t.format(concept=concept, metric=metric),
                    "authors": _authors(rng),
                    "journal": rng.choice(JOURNALS),
                    "year": year,
                    "pub_date": (
                        f"{year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}T00:00:00Z"
                    ),
                    # Forward-compat with subtask 05 (ignored by the model today):
                    "matched_terms": [term],
                    "sources": ["fixture"],
                }
            )
        (out_dir / f"{term}.json").write_text(json.dumps(papers, indent=2) + "\n", encoding="utf-8")
        print(f"  wrote {len(papers)} papers -> {out_dir / f'{term}.json'}")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Generate fake sample papers for --local runs.")
    ap.add_argument("--area", default="data_science")
    ap.add_argument("--count", type=int, default=5, help="papers per search term")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--search-terms-dir", type=Path, default=root / "data" / "search_terms")
    ap.add_argument("--fixtures-dir", type=Path, default=root / "data" / "fixtures")
    args = ap.parse_args()
    print(f"Generating {args.count} fake papers/term for area '{args.area}':")
    generate(args.area, args.count, args.seed, args.search_terms_dir, args.fixtures_dir)


if __name__ == "__main__":
    main()
