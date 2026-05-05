"""SQLite-backed session store for uploads and transcription sessions.

Replaces the in-memory dicts in api/state.py with a persistent store that
survives server restarts and supports TTL-based cleanup.

Schema
------
sessions(id TEXT PRIMARY KEY, type TEXT, data_json TEXT, status TEXT,
         created_at TEXT, expires_at TEXT)

uploads(id TEXT PRIMARY KEY, path TEXT, name TEXT, size_bytes INTEGER,
        created_at TEXT, expires_at TEXT)

TTL is 24 hours for both tables.  Call cleanup_expired() at startup.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tui_transcript.services.history import DB_DIR

# Re-use the same directory as history.db so we stay in one place.
SESSION_DB_PATH = DB_DIR / "sessions.db"

_TTL_HOURS = 24

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS uploads (
    id          TEXT PRIMARY KEY,
    path        TEXT NOT NULL,
    name        TEXT NOT NULL,
    size_bytes  INTEGER NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    data_json   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT NOT NULL
);
"""


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _expiry_utc() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=_TTL_HOURS)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


class SessionStore:
    """Persistent store for upload metadata and transcription sessions.

    The runtime queue/task objects (asyncio.Queue, asyncio.Task) are never
    persisted — they live only in memory inside each process.  Only the
    serialisable parts (job dicts, status) are written to SQLite so the
    server can recover session state after a restart.
    """

    def __init__(self, db_path: Path = SESSION_DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

        # In-process cache for live asyncio objects that cannot be serialised.
        # Keyed by session_id -> {"queue": asyncio.Queue, "task": asyncio.Task | None,
        #                         "jobs": list[VideoJob]}
        self._live: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_expired(self) -> int:
        """Delete sessions and uploads whose TTL has elapsed.

        Returns the total number of rows removed.
        """
        now = _now_utc()
        cur_s = self._conn.execute(
            "DELETE FROM sessions WHERE expires_at <= ?", (now,)
        )
        cur_u = self._conn.execute(
            "DELETE FROM uploads WHERE expires_at <= ?", (now,)
        )
        self._conn.commit()
        removed = cur_s.rowcount + cur_u.rowcount
        return removed

    # ------------------------------------------------------------------
    # Upload helpers
    # ------------------------------------------------------------------

    def store_upload(self, file_path: Path, original_name: str) -> str:
        """Persist upload metadata. Returns a new unique file_id."""
        fid = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO uploads (id, path, name, size_bytes, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (fid, str(file_path), original_name, file_path.stat().st_size, _expiry_utc()),
        )
        self._conn.commit()
        return fid

    def get_upload(self, file_id: str) -> dict[str, Any] | None:
        """Return upload metadata dict or None if not found / expired."""
        row = self._conn.execute(
            "SELECT path, name, size_bytes FROM uploads WHERE id = ?", (file_id,)
        ).fetchone()
        if row is None:
            return None
        return {"path": Path(row[0]), "name": row[1], "size_bytes": row[2]}

    def remove_upload(self, file_id: str) -> None:
        """Delete upload record and temp file from disk."""
        row = self._conn.execute(
            "SELECT path FROM uploads WHERE id = ?", (file_id,)
        ).fetchone()
        if row:
            p = Path(row[0])
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass
            self._conn.execute("DELETE FROM uploads WHERE id = ?", (file_id,))
            self._conn.commit()

    def list_uploads(self) -> list[dict[str, Any]]:
        """Return all active upload records."""
        rows = self._conn.execute(
            "SELECT id, path, name, size_bytes FROM uploads"
        ).fetchall()
        return [
            {"id": r[0], "path": Path(r[1]), "name": r[2], "size_bytes": r[3]}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def create_session(self, queue: asyncio.Queue, jobs: list) -> str:
        """Create a new transcription session. Returns session_id."""
        sid = str(uuid.uuid4())
        # Persist only the serialisable parts.
        data = {"jobs": [j.to_dict() for j in jobs], "status": "running"}
        self._conn.execute(
            "INSERT INTO sessions (id, data_json, status, expires_at) VALUES (?, ?, ?, ?)",
            (sid, json.dumps(data), "running", _expiry_utc()),
        )
        self._conn.commit()
        # Keep live objects in memory.
        self._live[sid] = {"queue": queue, "task": None, "jobs": jobs}
        return sid

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Return a session dict merging persisted status with live objects.

        Returns None if the session does not exist or has been cleaned up.
        The returned dict always has:
            queue   – asyncio.Queue (may be empty/closed if process restarted)
            task    – asyncio.Task | None
            jobs    – list of VideoJob objects (live) or dicts (restored)
            status  – str
        """
        row = self._conn.execute(
            "SELECT data_json, status FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None

        persisted_status = row[1]

        if session_id in self._live:
            live = self._live[session_id]
            return {
                "queue": live["queue"],
                "task": live["task"],
                "jobs": live["jobs"],
                "status": persisted_status,
            }

        # Session exists in DB but live objects are gone (e.g. after restart).
        # Return a minimal dict so callers can inspect status/jobs without crashing.
        data = json.loads(row[0])
        return {
            "queue": asyncio.Queue(),
            "task": None,
            "jobs": data.get("jobs", []),
            "status": persisted_status,
        }

    def set_session_task(self, session_id: str, task: asyncio.Task) -> None:
        """Attach an asyncio.Task to a live session (not persisted)."""
        if session_id in self._live:
            self._live[session_id]["task"] = task

    def complete_session(self, session_id: str) -> None:
        """Mark session status as 'done' in the DB."""
        self._conn.execute(
            "UPDATE sessions SET status = 'done' WHERE id = ?", (session_id,)
        )
        self._conn.commit()
        if session_id in self._live:
            # Keep live entry so the SSE stream can drain the queue.
            pass

    def cleanup_session(self, session_id: str) -> None:
        """Remove session and any uploads referenced by its jobs."""
        # Retrieve jobs to find associated uploads.
        session = self.get_session(session_id)
        if session:
            all_uploads = self.list_uploads()
            for job in session.get("jobs", []):
                # job can be a VideoJob object or a plain dict after restart.
                try:
                    job_path = str(job.path)  # VideoJob object
                except AttributeError:
                    job_path = str(job.get("path", ""))  # dict

                for entry in all_uploads:
                    if str(entry["path"]) == job_path:
                        self.remove_upload(entry["id"])
                        break

        self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._conn.commit()
        self._live.pop(session_id, None)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Module-level singleton (mirrors the previous implicit global state)
# ---------------------------------------------------------------------------

_store: SessionStore | None = None


def get_store() -> SessionStore:
    """Return the process-level singleton SessionStore, creating it on first call."""
    global _store
    if _store is None:
        _store = SessionStore()
        _store.cleanup_expired()
    return _store
