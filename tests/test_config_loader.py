"""Unit tests for the search-term loader and area discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from literature_digest.config import (
    AreaConfig,
    AreasFile,
    LoadedArea,
    SearchTerm,
    Settings,
    discover_areas,
)


def _write_term(base: Path, area: str, name: str, query: str) -> Path:
    area_dir = base / area
    area_dir.mkdir(parents=True, exist_ok=True)
    path = area_dir / f"{name}.txt"
    path.write_text(query, encoding="utf-8")
    return path


def test_discover_areas_returns_expected_terms(tmp_path: Path) -> None:
    _write_term(tmp_path, "data_science", "game_model", "TITLE-ABS-KEY(game model)")
    _write_term(tmp_path, "data_science", "tracking_data", "TITLE-ABS-KEY(tracking data)")
    _write_term(tmp_path, "nutrition", "empty", "   ")  # skipped

    settings = Settings(search_terms_dir=tmp_path)
    areas = discover_areas(settings)

    assert [a.slug for a in areas] == ["data_science"]
    assert [t.name for t in areas[0].terms] == ["game_model", "tracking_data"]
    assert areas[0].config.name == "Data Science"  # title-cased fallback


def test_discover_areas_skips_empty_and_disabled(tmp_path: Path) -> None:
    _write_term(tmp_path, "data_science", "term", "TITLE-ABS-KEY(x)")
    _write_term(tmp_path, "disabled_area", "term", "TITLE-ABS-KEY(y)")
    (tmp_path / "performance").mkdir()  # empty folder

    areas_file = AreasFile(
        defaults={"threshold": 60, "lookback_days": 17},
        areas=[
            AreaConfig(slug="disabled_area", name="Disabled Area", enabled=False),
        ],
    )
    settings = Settings(search_terms_dir=tmp_path)

    areas = discover_areas(settings, areas_file)

    assert [a.slug for a in areas] == ["data_science"]


def test_discover_areas_merges_metadata(tmp_path: Path) -> None:
    _write_term(tmp_path, "data_science", "term", "TITLE-ABS-KEY(x)")

    areas_file = AreasFile(
        defaults={"threshold": 60, "lookback_days": 17},
        areas=[
            AreaConfig(slug="data_science", name="Data Science", threshold=55),
        ],
    )
    settings = Settings(search_terms_dir=tmp_path)

    areas = discover_areas(settings, areas_file)

    assert len(areas) == 1
    assert areas[0].config.threshold == 55
    assert areas[0].config.name == "Data Science"


def test_discover_areas_skips_unparseable_terms_with_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_term(tmp_path, "data_science", "good", "TITLE-ABS-KEY(x)")
    _write_term(tmp_path, "data_science", "bad", "AUTHKEY(x)")

    settings = Settings(search_terms_dir=tmp_path)
    areas = discover_areas(settings)

    assert len(areas) == 1
    assert [t.name for t in areas[0].terms] == ["good"]
    captured = capsys.readouterr()
    assert "bad" in captured.out
    assert "skipped" in captured.out.lower()


def test_loaded_area_keywords_are_flattened_terms() -> None:
    loaded = LoadedArea(
        config=AreaConfig(slug="x", name="X"),
        terms=[
            SearchTerm(
                name="t1",
                raw_query="TITLE-ABS-KEY(a) OR TITLE-ABS-KEY(b)",
                path=Path("/tmp/t1.txt"),
            ),
            SearchTerm(
                name="t2",
                raw_query="TITLE-ABS-KEY(c)",
                path=Path("/tmp/t2.txt"),
            ),
        ],
    )
    assert loaded.keywords == ["a", "b", "c"]


def test_loaded_area_scopus_query_uses_first_raw_term() -> None:
    loaded = LoadedArea(
        config=AreaConfig(slug="x", name="X"),
        terms=[
            SearchTerm(name="t1", raw_query="TITLE-ABS-KEY(a)", path=Path("/tmp/t1.txt")),
            SearchTerm(name="t2", raw_query="TITLE-ABS-KEY(b)", path=Path("/tmp/t2.txt")),
        ],
    )
    assert loaded.scopus_query == "TITLE-ABS-KEY(a)"
