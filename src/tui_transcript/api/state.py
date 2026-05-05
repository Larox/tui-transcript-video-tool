"""API state — thin shim over the SQLite-backed SessionStore.

The public API is identical to the old in-memory implementation so that
routes need no changes.  All state is now persisted in
~/.tui_transcript/sessions.db via services/session_store.py.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from tui_transcript.services.session_store import get_store

# Temp directory for uploads (same as before; lifetime is the process)
_upload_dir: Path | None = None


def _get_upload_dir() -> Path:
    global _upload_dir
    if _upload_dir is None:
        _upload_dir = Path(tempfile.mkdtemp(prefix="tui_transcript_uploads_"))
    return _upload_dir


# ---------------------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------------------

def store_upload(file_path: Path, original_name: str) -> str:
    """Store an uploaded file. Returns unique ID."""
    return get_store().store_upload(file_path, original_name)


def get_upload(file_id: str) -> dict[str, Any] | None:
    """Get upload by ID."""
    return get_store().get_upload(file_id)


def remove_upload(file_id: str) -> None:
    """Remove upload and delete temp file."""
    get_store().remove_upload(file_id)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def create_session(queue: asyncio.Queue, jobs: list) -> str:
    """Create a transcription session. Returns session_id."""
    return get_store().create_session(queue, jobs)


def get_session(session_id: str) -> dict[str, Any] | None:
    """Get session by ID."""
    return get_store().get_session(session_id)


def set_session_task(session_id: str, task: asyncio.Task) -> None:
    """Store the pipeline task for a session."""
    get_store().set_session_task(session_id, task)


def complete_session(session_id: str) -> None:
    """Mark session as done."""
    get_store().complete_session(session_id)


def cleanup_session(session_id: str) -> None:
    """Remove session and cleanup uploads used by its jobs."""
    get_store().cleanup_session(session_id)
