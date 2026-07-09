"""Tests for the offline fixture source used by `run --local`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from literature_digest.config import AreaConfig, Settings
from literature_digest.sources.local import LocalSource


@pytest.fixture
def area() -> AreaConfig:
    return AreaConfig(
        slug="sports-nutrition",
        name="Sports Nutrition",
        keywords=["sports nutrition"],
        scopus_query="TITLE-ABS-KEY(...)",
    )


def _settings(fixtures_dir: Path) -> Settings:
    return Settings(fixtures_dir=fixtures_dir)


def test_search_loads_object_and_list(tmp_path: Path, area: AreaConfig) -> None:
    area_dir = tmp_path / area.slug
    area_dir.mkdir(parents=True)
    (area_dir / "one.json").write_text(
        json.dumps({"doi": "10.1/a", "title": "A"}), encoding="utf-8"
    )
    (area_dir / "two.json").write_text(
        json.dumps([{"doi": "10.1/b", "title": "B"}, {"doi": "10.1/c", "title": "C"}]),
        encoding="utf-8",
    )

    articles = LocalSource(_settings(tmp_path)).search(area, None)

    assert {a.doi for a in articles} == {"10.1/a", "10.1/b", "10.1/c"}
    # every fixture article is tagged with the fixture source and the area slug
    assert all("fixture" in a.sources for a in articles)
    assert all(a.area_slug == area.slug for a in articles)


def test_search_missing_area_dir_returns_empty(tmp_path: Path, area: AreaConfig) -> None:
    assert LocalSource(_settings(tmp_path)).search(area, None) == []


def test_enrich_is_noop(tmp_path: Path) -> None:
    assert LocalSource(_settings(tmp_path)).enrich("10.1/a") is None
