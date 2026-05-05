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

CREATE TABLE IF NOT EXISTS collections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    collection_type TEXT NOT NULL DEFAULT 'other',
    description     TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS collection_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    video_id      INTEGER NOT NULL REFERENCES processed_videos(id) ON DELETE CASCADE,
    position      INTEGER NOT NULL DEFAULT 0,
    added_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(collection_id, video_id)
);

CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#6b7280'
);

CREATE TABLE IF NOT EXISTS video_tags (
    video_id INTEGER NOT NULL REFERENCES processed_videos(id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (video_id, tag_id)
);

CREATE TABLE IF NOT EXISTS summaries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id     INTEGER NOT NULL REFERENCES processed_videos(id) ON DELETE CASCADE,
    text         TEXT    NOT NULL,
    generated_at TEXT    NOT NULL DEFAULT (datetime('now')),
    user_id      TEXT
);

CREATE TABLE IF NOT EXISTS qa_pairs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id   INTEGER NOT NULL REFERENCES processed_videos(id) ON DELETE CASCADE,
    question   TEXT    NOT NULL,
    answer     TEXT    NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    starred    INTEGER NOT NULL DEFAULT 0,
    user_id    TEXT
);

CREATE TABLE IF NOT EXISTS flashcards (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id   INTEGER NOT NULL REFERENCES processed_videos(id) ON DELETE CASCADE,
    concept    TEXT    NOT NULL,
    definition TEXT    NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    starred    INTEGER NOT NULL DEFAULT 0,
    user_id    TEXT
);

CREATE TABLE IF NOT EXISTS action_items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id       INTEGER NOT NULL REFERENCES processed_videos(id) ON DELETE CASCADE,
    text           TEXT    NOT NULL,
    urgency        TEXT    NOT NULL CHECK (urgency IN ('high', 'medium', 'low')),
    extracted_date TEXT,
    dismissed      INTEGER NOT NULL DEFAULT 0,
    user_id        TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fill_in_blank (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id   INTEGER NOT NULL REFERENCES processed_videos(id) ON DELETE CASCADE,
    sentence   TEXT    NOT NULL,
    answer     TEXT    NOT NULL,
    hint       TEXT    NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    starred    INTEGER NOT NULL DEFAULT 0,
    user_id    TEXT
);

CREATE TABLE IF NOT EXISTS true_false_statements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id    INTEGER NOT NULL REFERENCES processed_videos(id) ON DELETE CASCADE,
    statement   TEXT    NOT NULL,
    is_true     INTEGER NOT NULL DEFAULT 1,
    explanation TEXT    NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    starred     INTEGER NOT NULL DEFAULT 0,
    user_id     TEXT
);

CREATE TABLE IF NOT EXISTS error_detection_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id    INTEGER NOT NULL REFERENCES processed_videos(id) ON DELETE CASCADE,
    statement   TEXT    NOT NULL,
    error       TEXT    NOT NULL,
    correction  TEXT    NOT NULL,
    explanation TEXT    NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    starred     INTEGER NOT NULL DEFAULT 0,
    user_id     TEXT
);

CREATE TABLE IF NOT EXISTS study_sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date     TEXT    NOT NULL,
    cards_reviewed   INTEGER NOT NULL DEFAULT 0,
    quizzes_correct  INTEGER NOT NULL DEFAULT 0,
    quizzes_total    INTEGER NOT NULL DEFAULT 0,
    user_id          TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS study_sessions_date_user
    ON study_sessions (session_date, COALESCE(user_id, ''));

CREATE TABLE IF NOT EXISTS activity_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date      TEXT    NOT NULL,
    activity_type TEXT    NOT NULL,
    items_done    INTEGER NOT NULL DEFAULT 0,
    items_correct INTEGER NOT NULL DEFAULT 0,
    user_id       TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS activity_log_date_type_user
    ON activity_log (log_date, activity_type, COALESCE(user_id, ''));
"""

_FTS_SCHEMA = """\
CREATE VIRTUAL TABLE IF NOT EXISTS transcript_search
USING fts5(video_id UNINDEXED, output_title, source_path, content);
"""


class HistoryDB:
    """Lightweight SQLite store that remembers which videos have been processed."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.executescript(_FTS_SCHEMA)
        self._migrate()

    # ------------------------------------------------------------------
    # Migrations
    # ------------------------------------------------------------------

    def _migrate(self) -> None:
        """Apply incremental schema migrations for existing databases."""
        existing_tables = {
            row[0]
            for row in self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        # Add starred column to qa_pairs if missing
        if "qa_pairs" in existing_tables:
            cols = {
                row[1]
                for row in self._conn.execute("PRAGMA table_info(qa_pairs)").fetchall()
            }
            if "starred" not in cols:
                self._conn.execute(
                    "ALTER TABLE qa_pairs ADD COLUMN starred INTEGER NOT NULL DEFAULT 0"
                )
        # Add starred column to flashcards if missing
        if "flashcards" in existing_tables:
            cols = {
                row[1]
                for row in self._conn.execute(
                    "PRAGMA table_info(flashcards)"
                ).fetchall()
            }
            if "starred" not in cols:
                self._conn.execute(
                    "ALTER TABLE flashcards ADD COLUMN starred INTEGER NOT NULL DEFAULT 0"
                )
        # Add fill_in_blank table if missing (idempotent)
        self._conn.executescript(
            "CREATE TABLE IF NOT EXISTS fill_in_blank ("
            "    id         INTEGER PRIMARY KEY AUTOINCREMENT,"
            "    video_id   INTEGER NOT NULL REFERENCES processed_videos(id) ON DELETE CASCADE,"
            "    sentence   TEXT    NOT NULL,"
            "    answer     TEXT    NOT NULL,"
            "    hint       TEXT    NOT NULL DEFAULT '',"
            "    sort_order INTEGER NOT NULL DEFAULT 0,"
            "    starred    INTEGER NOT NULL DEFAULT 0,"
            "    user_id    TEXT"
            ");"
        )
        # Add true_false_statements table if missing (idempotent)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS true_false_statements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER NOT NULL REFERENCES processed_videos(id) ON DELETE CASCADE,
                statement TEXT NOT NULL,
                is_true INTEGER NOT NULL DEFAULT 1,
                explanation TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                starred INTEGER NOT NULL DEFAULT 0,
                user_id TEXT
            )
        """)
        # Add error_detection_items table if missing (idempotent)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS error_detection_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER NOT NULL REFERENCES processed_videos(id) ON DELETE CASCADE,
                statement TEXT NOT NULL,
                error TEXT NOT NULL,
                correction TEXT NOT NULL,
                explanation TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                starred INTEGER NOT NULL DEFAULT 0,
                user_id TEXT
            )
        """)
        # Seed activity_log from legacy study_sessions rows (treat each as activity_type='session')
        if "study_sessions" in existing_tables and "activity_log" in {
            row[0]
            for row in self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }:
            seeded = self._conn.execute(
                "SELECT COUNT(*) FROM activity_log WHERE activity_type = 'session'"
            ).fetchone()[0]
            if seeded == 0:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO activity_log
                        (log_date, activity_type, items_done, items_correct, user_id, created_at)
                    SELECT
                        session_date,
                        'session',
                        cards_reviewed,
                        quizzes_correct,
                        user_id,
                        created_at
                    FROM study_sessions
                    """
                )
        self._conn.commit()

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
    # Collections
    # ------------------------------------------------------------------

    def create_collection(
        self, name: str, collection_type: str = "other", description: str = ""
    ) -> dict:
        cur = self._conn.execute(
            "INSERT INTO collections (name, collection_type, description) "
            "VALUES (?, ?, ?)",
            (name, collection_type, description),
        )
        self._conn.commit()
        return self.get_collection(cur.lastrowid)  # type: ignore[arg-type]

    def get_collection(self, collection_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT id, name, collection_type, description, created_at, updated_at "
            "FROM collections WHERE id = ?",
            (collection_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "collection_type": row[2],
            "description": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }

    def list_collections(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT c.id, c.name, c.collection_type, c.description, "
            "c.created_at, c.updated_at, "
            "COUNT(ci.id) AS item_count "
            "FROM collections c "
            "LEFT JOIN collection_items ci ON ci.collection_id = c.id "
            "GROUP BY c.id ORDER BY c.updated_at DESC"
        ).fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "collection_type": r[2],
                "description": r[3],
                "created_at": r[4],
                "updated_at": r[5],
                "item_count": r[6],
            }
            for r in rows
        ]

    def update_collection(
        self,
        collection_id: int,
        *,
        name: str | None = None,
        collection_type: str | None = None,
        description: str | None = None,
    ) -> dict | None:
        updates: list[str] = []
        params: list = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if collection_type is not None:
            updates.append("collection_type = ?")
            params.append(collection_type)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if not updates:
            return self.get_collection(collection_id)
        updates.append("updated_at = datetime('now')")
        params.append(collection_id)
        self._conn.execute(
            f"UPDATE collections SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        self._conn.commit()
        return self.get_collection(collection_id)

    def delete_collection(self, collection_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM collections WHERE id = ?", (collection_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def add_collection_item(self, collection_id: int, video_id: int) -> None:
        max_pos = self._conn.execute(
            "SELECT COALESCE(MAX(position), -1) FROM collection_items "
            "WHERE collection_id = ?",
            (collection_id,),
        ).fetchone()[0]
        self._conn.execute(
            "INSERT OR IGNORE INTO collection_items (collection_id, video_id, position) "
            "VALUES (?, ?, ?)",
            (collection_id, video_id, max_pos + 1),
        )
        self._conn.commit()

    def remove_collection_item(self, collection_id: int, video_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM collection_items WHERE collection_id = ? AND video_id = ?",
            (collection_id, video_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def reorder_collection_items(
        self, collection_id: int, video_ids: list[int]
    ) -> None:
        for pos, vid in enumerate(video_ids):
            self._conn.execute(
                "UPDATE collection_items SET position = ? "
                "WHERE collection_id = ? AND video_id = ?",
                (pos, collection_id, vid),
            )
        self._conn.commit()

    def list_collection_items(self, collection_id: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT pv.id, pv.source_path, pv.output_title, pv.output_path, "
            "pv.language, pv.processed_at, ci.position "
            "FROM collection_items ci "
            "JOIN processed_videos pv ON pv.id = ci.video_id "
            "WHERE ci.collection_id = ? "
            "ORDER BY ci.position",
            (collection_id,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "source_path": r[1],
                "output_title": r[2],
                "output_path": r[3],
                "language": r[4],
                "processed_at": r[5],
                "position": r[6],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def create_tag(self, name: str, color: str = "#6b7280") -> dict:
        cur = self._conn.execute(
            "INSERT INTO tags (name, color) VALUES (?, ?)", (name, color)
        )
        self._conn.commit()
        return {"id": cur.lastrowid, "name": name, "color": color}

    def list_tags(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, color FROM tags ORDER BY name"
        ).fetchall()
        return [{"id": r[0], "name": r[1], "color": r[2]} for r in rows]

    def delete_tag(self, tag_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def add_video_tag(self, video_id: int, tag_id: int) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO video_tags (video_id, tag_id) VALUES (?, ?)",
            (video_id, tag_id),
        )
        self._conn.commit()

    def remove_video_tag(self, video_id: int, tag_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM video_tags WHERE video_id = ? AND tag_id = ?",
            (video_id, tag_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_video_tags(self, video_id: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT t.id, t.name, t.color FROM tags t "
            "JOIN video_tags vt ON vt.tag_id = t.id "
            "WHERE vt.video_id = ? ORDER BY t.name",
            (video_id,),
        ).fetchall()
        return [{"id": r[0], "name": r[1], "color": r[2]} for r in rows]

    # ------------------------------------------------------------------
    # Full-text search
    # ------------------------------------------------------------------

    def index_transcript(
        self, video_id: int, output_title: str, source_path: str, content: str
    ) -> None:
        """Add or replace a transcript in the FTS index."""
        self._conn.execute(
            "DELETE FROM transcript_search WHERE video_id = ?", (video_id,)
        )
        self._conn.execute(
            "INSERT INTO transcript_search (video_id, output_title, source_path, content) "
            "VALUES (?, ?, ?, ?)",
            (video_id, output_title, source_path, content),
        )
        self._conn.commit()

    def search_transcripts(
        self,
        query: str,
        *,
        collection_id: int | None = None,
        tag_name: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Full-text search across transcripts with optional filters."""
        if not query.strip():
            return []

        sql = (
            "SELECT ts.video_id, ts.output_title, ts.source_path, "
            "snippet(transcript_search, 3, '<mark>', '</mark>', '...', 40) AS excerpt, "
            "rank "
            "FROM transcript_search ts "
            "JOIN processed_videos pv ON pv.id = ts.video_id "
        )
        joins: list[str] = []
        conditions = ["transcript_search MATCH ?"]
        params: list = [query]

        if collection_id is not None:
            joins.append(
                "JOIN collection_items ci ON ci.video_id = ts.video_id"
            )
            conditions.append("ci.collection_id = ?")
            params.append(collection_id)

        if tag_name is not None:
            joins.append("JOIN video_tags vt ON vt.video_id = ts.video_id")
            joins.append("JOIN tags t ON t.id = vt.tag_id")
            conditions.append("t.name = ?")
            params.append(tag_name)

        sql += " ".join(joins) + " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [
            {
                "video_id": r[0],
                "output_title": r[1],
                "source_path": r[2],
                "excerpt": r[3],
                "rank": r[4],
            }
            for r in rows
        ]

    def get_video_by_source_and_prefix(
        self, source_path: str, prefix: str, output_mode: str
    ) -> dict | None:
        """Return the full processed_videos row for source+prefix+mode."""
        row = self._conn.execute(
            "SELECT id, source_path, output_title, output_path, language, processed_at "
            "FROM processed_videos "
            "WHERE source_path = ? AND prefix = ? AND output_mode = ?",
            (source_path, prefix, output_mode),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "source_path": row[1],
            "output_title": row[2],
            "output_path": row[3],
            "language": row[4],
            "processed_at": row[5],
        }

    def list_videos(self) -> list[dict]:
        """Return all processed videos for selection UIs."""
        rows = self._conn.execute(
            "SELECT id, source_path, output_title, output_path, language, processed_at "
            "FROM processed_videos ORDER BY processed_at DESC"
        ).fetchall()
        return [
            {
                "id": r[0],
                "source_path": r[1],
                "output_title": r[2],
                "output_path": r[3],
                "language": r[4],
                "processed_at": r[5],
            }
            for r in rows
        ]

    def get_video_by_id(self, video_id: int) -> dict | None:
        """Return a single processed_video row by id, or None."""
        row = self._conn.execute(
            "SELECT id, source_path, output_title, output_path, language, processed_at "
            "FROM processed_videos WHERE id = ?",
            (video_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "source_path": row[1],
            "output_title": row[2],
            "output_path": row[3],
            "language": row[4],
            "processed_at": row[5],
        }

    def get_transcript_content(self, video_id: int) -> str | None:
        """Return the full transcript text for *video_id* from the FTS index, or None."""
        row = self._conn.execute(
            "SELECT content FROM transcript_search WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        if row is None:
            return None
        return row[0]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()
