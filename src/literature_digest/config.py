"""Configuration loading for the literature-digest pipeline.

Reads `config/areas.yaml` and `config/organisation_context.md`, combines them
with environment variables (`.env`), and exposes typed settings to the rest of
the package via a single `Settings` object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from literature_digest.query import ParsedQuery, UnsupportedScopusSyntax, parse


class AreaConfig(BaseModel):
    """Thin per-area metadata stored in ``config/areas.yaml``."""

    slug: str
    name: str
    threshold: int | None = None
    enabled: bool = True


class AreasFile(BaseModel):
    """The parsed contents of ``config/areas.yaml``."""

    defaults: dict[str, int] = Field(default_factory=dict)
    areas: list[AreaConfig]

    def threshold_for(self, area: AreaConfig) -> int:
        """Resolve an area's threshold, falling back to the file default."""
        if area.threshold is not None:
            return area.threshold
        return int(self.defaults.get("threshold", 60))

    def lookback_days(self) -> int:
        return int(self.defaults.get("lookback_days", 17))


class SearchTerm(BaseModel):
    """One query loaded from ``data/search_terms/<area>/<term>.txt``."""

    name: str
    raw_query: str
    path: Path
    parsed: ParsedQuery | None = None


@dataclass
class LoadedArea:
    """An area discovered on disk plus its parsed search terms."""

    config: AreaConfig
    terms: list[SearchTerm] = field(default_factory=list)

    # Forward common config attributes so consumers can treat a LoadedArea like
    # the old AreaConfig.
    @property
    def slug(self) -> str:
        return self.config.slug

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def threshold(self) -> int | None:
        return self.config.threshold

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @property
    def keywords(self) -> list[str]:
        """Flattened distinct content terms, useful for free-text API sources."""
        seen: set[str] = set()
        keywords: list[str] = []
        for term in self.terms:
            parsed = term.parsed
            if parsed is None:
                try:
                    parsed = parse(term.raw_query, term_name=term.name)
                except UnsupportedScopusSyntax:
                    continue
            for t in parsed.terms:
                if t not in seen:
                    seen.add(t)
                    keywords.append(t)
        return keywords

    @property
    def scopus_query(self) -> str:
        """Best-effort Scopus query string for the API source.

        Currently returns the first term's raw query; multi-term areas can be
        joined later once the pipeline supports disjunctive Scopus searches.
        """
        if not self.terms:
            return ""
        return self.terms[0].raw_query


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
    search_terms_dir: Annotated[Path, Field(default=Path("./data/search_terms"))]


def load_areas(path: Path | None = None) -> AreasFile:
    """Load and validate ``config/areas.yaml``."""
    path = path or Settings().areas_config
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AreasFile.model_validate(raw)


def load_org_context(path: Path | None = None) -> str:
    """Load ``config/organisation_context.md`` as a plain string for prompt injection."""
    path = path or Settings().org_context
    return path.read_text(encoding="utf-8")


def discover_areas(
    settings: Settings | None = None,
    areas_file: AreasFile | None = None,
) -> list[LoadedArea]:
    """Discover areas and their search terms from disk.

    Steps:
        1. List subdirectories of ``settings.search_terms_dir``.
        2. Read ``*.txt`` files in each (skip empties / unparseable terms).
        3. Merge with ``areas.yaml`` metadata (optional / partial).
        4. Drop disabled areas and areas with zero valid terms.
    """
    settings = settings or Settings()
    areas_file = areas_file or load_areas(settings.areas_config)
    metadata = {a.slug: a for a in areas_file.areas}

    loaded: list[LoadedArea] = []
    if not settings.search_terms_dir.exists():
        return loaded

    for subdir in sorted(settings.search_terms_dir.iterdir()):
        if not subdir.is_dir():
            continue
        slug = subdir.name
        config = metadata.get(slug)
        if config is None:
            config = AreaConfig(
                slug=slug,
                name=slug.replace("_", " ").title(),
            )
        if not config.enabled:
            continue

        terms: list[SearchTerm] = []
        for path in sorted(subdir.glob("*.txt")):
            raw = path.read_text(encoding="utf-8").strip()
            if not raw:
                continue
            name = path.stem
            try:
                parsed = parse(raw, term_name=name)
            except UnsupportedScopusSyntax as exc:
                # Surface as a skipped term with a clear warning.  Using print
                # keeps this module free of Rich/CLI dependencies.
                print(f"WARNING: skipped {slug}/{name}.txt: {exc.detail}")
                continue
            terms.append(
                SearchTerm(
                    name=name,
                    raw_query=raw,
                    path=path,
                    parsed=parsed,
                )
            )

        if not terms:
            continue
        loaded.append(LoadedArea(config=config, terms=terms))

    return loaded
