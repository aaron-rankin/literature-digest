"""Skeleton smoke tests: verify imports, store round-trip, and end-to-end run."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_all_modules_import_cleanly() -> None:
    """Every module in the package must import without errors."""
    modules = [
        "literature_digest.cli",
        "literature_digest.config",
        "literature_digest.models",
        "literature_digest.pipeline",
        "literature_digest.report",
        "literature_digest.screen",
        "literature_digest.store",
        "literature_digest.summarize",
        "literature_digest.sources.crossref",
        "literature_digest.sources.dedupe",
        "literature_digest.sources.openalex",
        "literature_digest.sources.scopus_api",
        "literature_digest.sources.scopus_email",
    ]
    for name in modules:
        importlib.import_module(name)


def test_store_seen_doi_round_trip(tmp_path: Path) -> None:
    from literature_digest.store import Store

    with Store(tmp_path / "state.db") as store:
        assert not store.is_seen("10.1234/test", "sports-nutrition")
        store.mark_seen("10.1234/test", "sports-nutrition")
        assert store.is_seen("10.1234/test", "sports-nutrition")
        # Different area: same DOI is not yet seen there
        assert not store.is_seen("10.1234/test", "recovery-and-sleep")


def test_store_last_run_round_trip(tmp_path: Path) -> None:
    from datetime import datetime

    from literature_digest.store import Store

    with Store(tmp_path / "state.db") as store:
        assert store.get_last_run("sports-nutrition") is None
        store.set_last_run("sports-nutrition")
        assert store.get_last_run("sports-nutrition") is not None
        assert isinstance(store.get_last_run("sports-nutrition"), datetime)


def test_pipeline_run_produces_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end smoke: with network sources stubbed, the pipeline must still run
    and produce an index.html + one area HTML per configured area."""
    from literature_digest.pipeline import run_all
    from literature_digest.sources.crossref import CrossrefSource
    from literature_digest.sources.openalex import OpenAlexSource
    from literature_digest.sources.scopus_api import ScopusApiSource

    # Keep this an offline orchestration/render smoke test: the sources now make
    # real HTTP calls, so stub them back to empty for this test.
    monkeypatch.setattr(ScopusApiSource, "search", lambda self, source_query, window: [])
    monkeypatch.setattr(OpenAlexSource, "search", lambda self, source_query, window: [])
    monkeypatch.setattr(CrossrefSource, "search", lambda self, source_query, window: [])

    # Point the pipeline at a tmp data dir so we don't touch the repo's data/.
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    # Use the repo's real config/areas.yaml and templates/.
    repo_root = Path(__file__).resolve().parent.parent
    monkeypatch.setenv("AREAS_CONFIG", str(repo_root / "config" / "areas.yaml"))
    monkeypatch.setenv("ORG_CONTEXT", str(repo_root / "config" / "organisation_context.md"))

    index_path = run_all()
    assert index_path.exists()
    assert (tmp_path / "data" / "reports" / "areas" / "data_science.html").exists()
    html = index_path.read_text(encoding="utf-8")
    assert "Data Science" in html
