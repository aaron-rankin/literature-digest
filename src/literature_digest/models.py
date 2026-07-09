"""Domain models for the literature-digest pipeline.

A single `Article` flows through every stage. Each source populates the fields
it can; downstream stages read the same object. Screening and action-point
fields stay `None` until the LLM stages fill them in.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ScreeningResult(BaseModel):
    """LLM-produced relevancy assessment for one article."""

    score: int = Field(ge=0, le=100, description="Relevancy score 0-100")
    category: Literal["directly actionable", "monitoring", "background"]
    rationale: str = Field(description="1-2 sentence justification")


class ActionPoint(BaseModel):
    """One actionable takeaway extracted from an article."""

    text: str
    category: Literal["directly actionable", "monitoring", "background"]


class Article(BaseModel):
    """A single research article moving through the pipeline."""

    model_config = ConfigDict(extra="ignore")

    # Identity & metadata (filled by ingestion sources)
    doi: str | None = Field(default=None, description="Normalized DOI (no URL prefix)")
    title: str | None = None
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    journal: str | None = None
    year: int | None = None
    url: HttpUrl | None = None
    pub_date: datetime | None = None

    # Provenance
    sources: list[str] = Field(
        default_factory=list,
        description="Ingestion sources contributing metadata (e.g. ['scopus_email','openalex'])",
    )

    # LLM-stage outputs (None until populated)
    screening: ScreeningResult | None = None
    action_points: list[ActionPoint] = Field(default_factory=list)

    # Bookkeeping
    area_slug: str | None = None

    @property
    def citation(self) -> str:
        """Short human-readable citation for the report."""
        first_author = self.authors[0] if self.authors else "Unknown"
        et_al = " et al." if len(self.authors) > 1 else ""
        year = f" ({self.year})" if self.year else ""
        journal = f". {self.journal}" if self.journal else ""
        return f"{first_author}{et_al}{year}{journal}"
