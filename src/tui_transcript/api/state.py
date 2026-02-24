"""In-memory state for uploads and transcription sessions."""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path
from typing import Any

# Uploaded files: id -> {path, name, size_bytes}
_uploads: dict[str, dict[str, Any]] = {}

# Sessions: session_id -> {queue, task, jobs, status}
_sessions: dict[str, dict[str, Any]] = {}

# Temp directory for uploads (cleaned on shutdown)
_upload_dir: Path | None = None


def _get_upload_dir() -> Path:
    global _upload_dir
    if _upload_dir is None:
        _upload_dir = Path(tempfile.mkdtemp(prefix="tui_transcript_uploads_"))
    return _upload_dir


def store_upload(file_path: Path, original_name: str) -> str:
    """Store an uploaded file. Returns unique ID."""
    fid = str(uuid.uuid4())
    _uploads[fid] = {
        "path": file_path,
        "name": original_name,
        "size_bytes": file_path.stat().st_size,
    }
    return fid


def get_upload(file_id: str) -> dict[str, Any] | None:
    """Get upload by ID."""
    return _uploads.get(file_id)


def remove_upload(file_id: str) -> None:
    """Remove upload and delete temp file."""
    entry = _uploads.pop(file_id, None)
    if entry and entry["path"].exists():
        try:
            entry["path"].unlink()
        except OSError:
            pass


def create_session(queue: asyncio.Queue, jobs: list) -> str:
    """Create a transcription session. Returns session_id."""
    sid = str(uuid.uuid4())
    _sessions[sid] = {
        "queue": queue,
        "task": None,
        "jobs": jobs,
        "status": "running",
    }
    return sid


def get_session(session_id: str) -> dict[str, Any] | None:
    """Get session by ID."""
    return _sessions.get(session_id)


def set_session_task(session_id: str, task: asyncio.Task) -> None:
    """Store the pipeline task for a session."""
    if s := _sessions.get(session_id):
        s["task"] = task


def complete_session(session_id: str) -> None:
    """Mark session as done."""
    if s := _sessions.get(session_id):
        s["status"] = "done"


def cleanup_session(session_id: str) -> None:
    """Remove session and cleanup uploads used by its jobs."""
    s = _sessions.pop(session_id, None)
    if s and "jobs" in s:
        for job in s["jobs"]:
            path_str = str(job.path)
            for fid, entry in list(_uploads.items()):
                if str(entry["path"]) == path_str:
                    remove_upload(fid)
                    break
