"""Shared fixtures for tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.collection_store import CollectionStore


@pytest.fixture()
def db(tmp_path: Path) -> HistoryDB:
    """Fresh in-memory-like SQLite DB in a temp dir."""
    db = HistoryDB(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture()
def store(db: HistoryDB) -> CollectionStore:
    """CollectionStore backed by the test DB."""
    s = CollectionStore(db=db)
    yield s
    # db fixture handles close


def _insert_video(db: HistoryDB, idx: int = 1) -> int:
    """Helper: insert a processed_video row and return its id."""
    db.record(
        source_path=f"/videos/lecture_{idx}.mp4",
        prefix="Test",
        naming_mode="sequential",
        sequential_number=idx,
        output_title=f"Lecture {idx}",
        output_mode="markdown",
        output_path=f"/output/Lecture_{idx}.md",
        language="en",
    )
    row = db._conn.execute(
        "SELECT id FROM processed_videos WHERE source_path = ?",
        (f"/videos/lecture_{idx}.mp4",),
    ).fetchone()
    return row[0]
