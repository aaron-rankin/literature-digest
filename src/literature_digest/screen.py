"""LLM relevancy screening.

Contract:
    screen(article, area, org_context) -> ScreeningResult

For each article, calls LiteLLM with `{title, abstract, area.keywords,
organisation_context.md}` and returns a structured ScreeningResult:
- score (0-100)
- category (directly actionable | monitoring | background)
- rationale (1-2 sentences)

Articles scoring below `area.threshold` are dropped by the pipeline; the rest
flow into `summarize.py` for action-point extraction.

Phase 4 will implement:
- LiteLLM `completion()` call with `response_format` JSON schema
- Pydantic validation of the parsed JSON
- Retry on malformed JSON (max 2 retries, temperature 0)
"""

from __future__ import annotations

from literature_digest.config import AreaConfig, Settings
from literature_digest.models import Article, ScreeningResult

SCREEN_PROMPT = """\
You are screening scientific articles for an elite-sports performance organisation.

ORGANISATION CONTEXT:
{org_context}

RESEARCH AREA: {area_name}
AREA KEYWORDS: {keywords}

ARTICLE TITLE: {title}
ARTICLE ABSTRACT: {abstract}

Score this article's relevancy to the organisation from 0 to 100 and classify it
as one of:
- directly actionable : could change practice within 12 months
- monitoring         : worth tracking but not ready to adopt
- background         : contextual only

Return JSON with keys: score (int 0-100), category (one of the three),
rationale (1-2 sentence string)."""


class LLMClient:
    """Thin wrapper over LiteLLM with JSON-schema-validated responses.

    Centralizing the call here means swapping OpenAI / Claude / Ollama later
    is a single env-var change (`LIT_MODEL`), not an edit in every consumer.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def complete_json(self, prompt: str, schema: dict) -> dict:
        """Call the configured LLM and parse the response as JSON.

        PLACEHOLDER: returns an empty dict. Phase 4 will wire up
        `litellm.completion(model=self.settings.lit_model, ...)`,
        request `response_format={"type": "json_object"}`, parse the content,
        and retry once on JSONDecodeError.
        """
        # TODO(phase-4): implement litellm.completion + JSON validation
        _ = (prompt, schema)
        return {}


class Screener:
    """LLM-powered relevancy screener. Placeholder body."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def screen(self, article: Article, area: AreaConfig, org_context: str) -> ScreeningResult:
        """Return a ScreeningResult for `article`.

        PLACEHOLDER: returns a neutral "monitoring" result at the threshold so
        the pipeline can be exercised end-to-end without an API call. Phase 4
        will replace this with a real LLM call.
        """
        _ = self.client.complete_json(
            SCREEN_PROMPT.format(
                org_context=org_context,
                area_name=area.name,
                keywords=", ".join(area.keywords),
                title=article.title or "",
                abstract=article.abstract or "",
            ),
            schema={},  # TODO(phase-4): real JSON schema
        )
        return ScreeningResult(
            score=area.threshold if area.threshold else 60,
            category="monitoring",
            rationale="PLACEHOLDER: real screening not yet implemented.",
        )
