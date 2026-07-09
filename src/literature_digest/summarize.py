"""LLM action-point extraction.

Contract:
    summarize(article, org_context) -> list[ActionPoint]

For each article that passed screening, calls LiteLLM with the title, abstract,
screening rationale, and organisation context. Returns 1-3 short action points
written as imperatives for a coach or sports scientist, each tagged with the
same category taxonomy as screening.
"""

from __future__ import annotations

from literature_digest.models import ActionPoint, Article
from literature_digest.screen import LLMClient

SUMMARIZE_PROMPT = """\
You are extracting action points for an elite-sports performance organisation.

ORGANISATION CONTEXT:
{org_context}

ARTICLE TITLE: {title}
ARTICLE ABSTRACT: {abstract}
SCREENING RATIONALE: {rationale}

Return 1-3 action points as JSON: {{"action_points": [{{"text": "...",
"category": "directly actionable|monitoring|background"}}]}}.
Each `text` should be one imperative sentence aimed at a coach or sports
scientist (e.g. "Trial X with Y population for Z weeks before adopting.")."""

SUMMARIZE_SCHEMA = {
    "type": "object",
    "properties": {
        "action_points": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["directly actionable", "monitoring", "background"],
                    },
                },
                "required": ["text", "category"],
            },
        },
    },
    "required": ["action_points"],
}


class Summarizer:
    """LLM-powered action-point extractor."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def summarize(self, article: Article, org_context: str) -> list[ActionPoint]:
        """Return up to 3 deduplicated ActionPoints for `article`."""
        rationale = (
            article.screening.rationale if article.screening else "No screening yet."
        )
        data = self.client.complete_json(
            SUMMARIZE_PROMPT.format(
                org_context=org_context,
                title=article.title or "",
                abstract=article.abstract or "",
                rationale=rationale,
            ),
            schema=SUMMARIZE_SCHEMA,
        )
        points = [ActionPoint.model_validate(p) for p in data.get("action_points", [])]

        deduped: list[ActionPoint] = []
        seen_texts: set[str] = set()
        for point in points:
            key = point.text.strip().lower()
            if not key or key in seen_texts:
                continue
            seen_texts.add(key)
            deduped.append(point)
        return deduped[:3]
