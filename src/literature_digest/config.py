"""Configuration loading for the literature-digest pipeline.

Reads `config/areas.yaml` and `config/organisation_context.md`, combines them
with environment variables (`.env`), and exposes typed settings to the rest of
the package via a single `Settings` object.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AreaConfig(BaseModel):
    """A single research area tracked by the pipeline."""

    slug: str
    name: str
    keywords: list[str]
    scopus_query: str
    threshold: int | None = None


class AreasFile(BaseModel):
    """The parsed contents of `config/areas.yaml`."""

    defaults: dict[str, int] = Field(default_factory=dict)
    areas: list[AreaConfig]

    def threshold_for(self, area: AreaConfig) -> int:
        """Resolve an area's threshold, falling back to the file default."""
        if area.threshold is not None:
            return area.threshold
        return int(self.defaults.get("threshold", 60))

    def lookback_days(self) -> int:
        return int(self.defaults.get("lookback_days", 17))


class Settings(BaseSettings):
    """Environment-derived settings. Loaded from `.env` if present."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # IMAP
    imap_host: Annotated[str, Field(default="")]
    imap_port: Annotated[int, Field(default=993)]
    imap_user: Annotated[str, Field(default="")]
    imap_password: Annotated[str, Field(default="")]
    imap_processed_folder: Annotated[str, Field(default="Processed")]

    # Scopus API
    scopus_api_key: Annotated[str, Field(default="")]
    scopus_inst_token: Annotated[str, Field(default="")]

    # LLM (LiteLLM — provider-agnostic)
    lit_model: Annotated[str, Field(default="openai/gpt-4o-mini")]
    lit_api_key: Annotated[str, Field(default="")]
    lit_api_base: Annotated[str, Field(default="")]

    # Polite pool identification
    contact_email: Annotated[str, Field(default="")]

    # Paths
    data_dir: Annotated[Path, Field(default=Path("./data"))]
    areas_config: Annotated[Path, Field(default=Path("./config/areas.yaml"))]
    org_context: Annotated[Path, Field(default=Path("./config/organisation_context.md"))]
    # Offline fixtures for `run --local` (one <area_slug>/ subdir of Article JSON each)
    fixtures_dir: Annotated[Path, Field(default=Path("./data/fixtures"))]


def load_areas(path: Path | None = None) -> AreasFile:
    """Load and validate `config/areas.yaml`."""
    path = path or Settings().areas_config
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AreasFile.model_validate(raw)


def load_org_context(path: Path | None = None) -> str:
    """Load `config/organisation_context.md` as a plain string for prompt injection."""
    path = path or Settings().org_context
    return path.read_text(encoding="utf-8")
