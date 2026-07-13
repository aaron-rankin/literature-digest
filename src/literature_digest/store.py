"""SQLite state store for idempotent pipeline runs.

Three responsibilities:
1. `seen_dois`  - skip articles already processed (prevents duplicates across overlapping runs)
2. `runs`       - log every pipeline execution (area, timestamp, counts)
3. `area_state` - per-area `last_run` timestamp, used to scope IMAP/API queries

Uses stdlib sqlite3 - no extra dependency. Schema created lazily on first connect.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_dois (
    doi        TEXT PRIMARY KEY,
    area_slug  TEXT NOT NULL,
    first_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    area_slug    TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    ingested     INTEGER DEFAULT 0,
    retained     INTEGER DEFAULT 0,
    dropped      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS area_state (
    area_slug TEXT PRIMARY KEY,
    last_run  TEXT NOT NULL
);
"""


class Store:
    """Thin wrapper around the pipeline's SQLite database."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ── seen_dois ─────────────────────────────────────────────────────────
    def is_seen(self, doi: str, area_slug: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM seen_dois WHERE doi = ? AND area_slug = ?",
            (doi, area_slug),
        ).fetchone()
        return row is not None

    def mark_seen(self, doi: str, area_slug: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO seen_dois (doi, area_slug, first_seen) VALUES (?, ?, ?)",
            (doi, area_slug, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()

    # ── area_state ────────────────────────────────────────────────────────
    def get_last_run(self, area_slug: str) -> datetime | None:
        row = self._conn.execute(
            "SELECT last_run FROM area_state WHERE area_slug = ?",
            (area_slug,),
        ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def set_last_run(self, area_slug: str, when: datetime | None = None) -> None:
        when = when or datetime.now(UTC)
        self._conn.execute(
            "INSERT INTO area_state (area_slug, last_run) VALUES (?, ?) "
            "ON CONFLICT(area_slug) DO UPDATE SET last_run = excluded.last_run",
            (area_slug, when.isoformat()),
        )
        self._conn.commit()

    # ── runs ──────────────────────────────────────────────────────────────
    def start_run(self, area_slug: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO runs (area_slug, started_at) VALUES (?, ?)",
            (area_slug, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, *, ingested: int, retained: int, dropped: int) -> None:
        self._conn.execute(
            "UPDATE runs SET finished_at = ?, ingested = ?, retained = ?, dropped = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), ingested, retained, dropped, run_id),
        )
        self._conn.commit()
