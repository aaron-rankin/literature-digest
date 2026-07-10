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
"""

from __future__ import annotations

import json
import re

import litellm

from literature_digest.config import LoadedArea, Settings
from literature_digest.models import Article, ScreeningResult

# Local models (Ollama etc.) often wrap JSON in ```fences``` or prepend
# chain-of-thought text before the object. Pull the last top-level {...} blob
# out of the response rather than assuming the whole content is clean JSON.
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

SCREEN_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "category": {
            "type": "string",
            "enum": ["directly actionable", "monitoring", "background"],
        },
        "rationale": {"type": "string"},
    },
    "required": ["score", "category", "rationale"],
}

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

    def complete_json(self, prompt: str, schema: dict, max_retries: int = 2) -> dict:
        """Call the configured LLM and parse the response as a JSON object.

        Retries up to `max_retries` times (temperature 0) if the response is
        not valid JSON — local models without native JSON mode occasionally
        wrap the object in prose or markdown fences.
        """
        _ = schema  # prompts already spell out the required keys
        kwargs: dict = {
            "model": self.settings.lit_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        if self.settings.lit_api_key:
            kwargs["api_key"] = self.settings.lit_api_key
        if self.settings.lit_api_base:
            kwargs["api_base"] = self.settings.lit_api_base

        last_error: Exception | None = None
        for _attempt in range(max_retries + 1):
            try:
                response = litellm.completion(**kwargs)
                content = response.choices[0].message.content or ""
                return _extract_json(content)
            except (json.JSONDecodeError, IndexError, AttributeError, TypeError) as exc:
                last_error = exc
                continue
        msg = f"LLM response was not valid JSON after retries: {last_error}"
        raise RuntimeError(msg) from last_error


def _extract_json(text: str) -> dict:
    """Parse `text` as JSON, tolerating markdown fences and leading prose."""
    match = _JSON_BLOCK.search(text)
    candidate = match.group(0) if match else text
    return json.loads(candidate)


class Screener:
    """LLM-powered relevancy screener."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def screen(self, article: Article, area: LoadedArea, org_context: str) -> ScreeningResult:
        """Return a ScreeningResult for `article`."""
        data = self.client.complete_json(
            SCREEN_PROMPT.format(
                org_context=org_context,
                area_name=area.name,
                keywords=", ".join(area.keywords),
                title=article.title or "",
                abstract=article.abstract or "",
            ),
            schema=SCREEN_SCHEMA,
        )
        return ScreeningResult.model_validate(data)
