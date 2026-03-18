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

CREATE TABLE IF NOT EXISTS output_directories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    path       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS document_highlights (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT    NOT NULL UNIQUE,
    output_path TEXT    NOT NULL UNIQUE,
    moments     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
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

    def get_processed_record(
        self, source_path: str, prefix: str, output_mode: str
    ) -> dict | None:
        """Return output_path, doc_id, doc_url for an already-processed file, or None."""
        row = self._conn.execute(
            "SELECT output_path, doc_id, doc_url FROM processed_videos "
            "WHERE source_path = ? AND prefix = ? AND output_mode = ?",
            (source_path, prefix, output_mode),
        ).fetchone()
        if row is None:
            return None
        return {
            "output_path": row[0] or "",
            "doc_id": row[1] or "",
            "doc_url": row[2] or "",
        }

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
    # Output directories
    # ------------------------------------------------------------------

    def register_directory(self, name: str, path: str) -> int:
        """Register an output directory. Returns its id.

        If *path* is already registered, returns the existing row id.
        """
        row = self._conn.execute(
            "SELECT id FROM output_directories WHERE path = ?", (path,)
        ).fetchone()
        if row is not None:
            return row[0]
        cur = self._conn.execute(
            "INSERT INTO output_directories (name, path) VALUES (?, ?)",
            (name, path),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def unregister_directory(self, dir_id: int) -> bool:
        """Remove a directory registration. Returns True if a row was deleted."""
        cur = self._conn.execute(
            "DELETE FROM output_directories WHERE id = ?", (dir_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def update_directory_path(self, dir_id: int, new_path: str) -> bool:
        """Re-attach a directory to a new filesystem path."""
        cur = self._conn.execute(
            "UPDATE output_directories SET path = ? WHERE id = ?",
            (new_path, dir_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_directories(self) -> list[dict]:
        """Return all registered directories as dicts."""
        cur = self._conn.execute(
            "SELECT id, name, path, created_at FROM output_directories "
            "ORDER BY created_at"
        )
        return [
            {"id": r[0], "name": r[1], "path": r[2], "created_at": r[3]}
            for r in cur.fetchall()
        ]

    def get_directory(self, dir_id: int) -> dict | None:
        """Return a single directory by id, or None."""
        row = self._conn.execute(
            "SELECT id, name, path, created_at FROM output_directories WHERE id = ?",
            (dir_id,),
        ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "name": row[1], "path": row[2], "created_at": row[3]}

    # ------------------------------------------------------------------
    # Document highlights
    # ------------------------------------------------------------------

    def save_highlights(
        self, slug: str, output_path: str, moments: list[dict]
    ) -> None:
        """Persist key moments for a document. Upserts on slug conflict."""
        import json as _json

        self._conn.execute(
            "INSERT INTO document_highlights (slug, output_path, moments) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(slug) DO UPDATE SET moments = excluded.moments",
            (slug, output_path, _json.dumps(moments, ensure_ascii=False)),
        )
        self._conn.commit()

    def get_highlights_by_slug(self, slug: str) -> dict | None:
        """Return {id, slug, moments} for *slug*, or None if not found."""
        import json as _json

        row = self._conn.execute(
            "SELECT id, slug, moments FROM document_highlights WHERE slug = ?",
            (slug,),
        ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "slug": row[1], "moments": _json.loads(row[2])}

    def get_highlights_ref_for_path(self, output_path: str) -> dict | None:
        """Return {id, slug} for the given output_path, or None if not found."""
        row = self._conn.execute(
            "SELECT id, slug FROM document_highlights WHERE output_path = ?",
            (output_path,),
        ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "slug": row[1]}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()
