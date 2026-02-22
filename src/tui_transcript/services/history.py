from __future__ import annotations

import sqlite3
from pathlib import Path


DB_DIR = Path.home() / ".tui_transcript"
DB_PATH = DB_DIR / "history.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS processed_videos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path       TEXT NOT NULL,
    prefix            TEXT NOT NULL,
    naming_mode       TEXT NOT NULL,
    sequential_number INTEGER,
    output_title      TEXT NOT NULL,
    output_mode       TEXT NOT NULL,
    output_path       TEXT,
    doc_id            TEXT,
    doc_url           TEXT,
    language          TEXT,
    processed_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class HistoryDB:
    """Lightweight SQLite store that remembers which videos have been processed."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_next_sequential_number(self, prefix: str) -> int:
        """Return the next available 1-based sequential number for *prefix*."""
        row = self._conn.execute(
            "SELECT COALESCE(MAX(sequential_number), 0) "
            "FROM processed_videos "
            "WHERE prefix = ? AND naming_mode = 'sequential'",
            (prefix,),
        ).fetchone()
        return row[0] + 1

    def is_already_processed(
        self, source_path: str, prefix: str, output_mode: str
    ) -> bool:
        """True if this exact source+prefix+mode combo was already exported."""
        row = self._conn.execute(
            "SELECT 1 FROM processed_videos "
            "WHERE source_path = ? AND prefix = ? AND output_mode = ?",
            (source_path, prefix, output_mode),
        ).fetchone()
        return row is not None

    def get_output_title_exists(
        self, output_title: str, output_mode: str
    ) -> bool:
        """True if *output_title* was already used for the given mode."""
        row = self._conn.execute(
            "SELECT 1 FROM processed_videos "
            "WHERE output_title = ? AND output_mode = ?",
            (output_title, output_mode),
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        source_path: str,
        prefix: str,
        naming_mode: str,
        sequential_number: int | None,
        output_title: str,
        output_mode: str,
        output_path: str | None = None,
        doc_id: str | None = None,
        doc_url: str | None = None,
        language: str | None = None,
    ) -> None:
        """Persist a successfully-processed job."""
        self._conn.execute(
            "INSERT INTO processed_videos "
            "(source_path, prefix, naming_mode, sequential_number, "
            " output_title, output_mode, output_path, doc_id, doc_url, language) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source_path,
                prefix,
                naming_mode,
                sequential_number,
                output_title,
                output_mode,
                output_path,
                doc_id,
                doc_url,
                language,
            ),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()
