"""End-to-end ingest pipeline with FakeEmbedder + FakeVectorStore."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.embedder import FakeEmbedder
from tui_transcript.services.rag.ingest import (
    ingest_file,
    reindex_transcript,
)
from tui_transcript.services.rag.store import FakeVectorStore


def _seed_collection(db: HistoryDB) -> int:
    db._conn.execute(
        "INSERT INTO collections (name, collection_type, description, created_at, updated_at) "
        "VALUES ('M', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    return db._conn.execute("SELECT id FROM collections").fetchone()[0]


def _insert_file(db: HistoryDB, collection_id: int, storage_path: Path) -> int:
    size = storage_path.stat().st_size if storage_path.exists() else 0
    cur = db._conn.execute(
        "INSERT INTO materia_files "
        "(collection_id, filename, storage_path, mime_type, size_bytes, status, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (
            collection_id,
            storage_path.name,
            str(storage_path),
            "application/pdf",
            size,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    db._conn.commit()
    return cur.lastrowid


def test_ingest_pdf_writes_chunks_and_marks_indexed(db: HistoryDB) -> None:
    cid = _seed_collection(db)
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    fid = _insert_file(db, cid, pdf)

    store = FakeVectorStore()
    embedder = FakeEmbedder()

    ingest_file(file_id=fid, db=db, embedder=embedder, store=store)

    row = db._conn.execute(
        "SELECT status, indexed_at FROM materia_files WHERE id = ?", (fid,)
    ).fetchone()
    assert row[0] == "indexed"
    assert row[1] is not None
    assert len(store._items) >= 2


def test_ingest_is_idempotent(db: HistoryDB) -> None:
    cid = _seed_collection(db)
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    fid = _insert_file(db, cid, pdf)

    store = FakeVectorStore()
    embedder = FakeEmbedder()
    ingest_file(file_id=fid, db=db, embedder=embedder, store=store)
    n1 = len(store._items)
    ingest_file(file_id=fid, db=db, embedder=embedder, store=store)
    n2 = len(store._items)
    assert n1 == n2


def test_ingest_marks_error_on_extractor_failure(db: HistoryDB) -> None:
    cid = _seed_collection(db)
    bad = Path("/no/such.pdf")
    fid = _insert_file(db, cid, bad)
    store = FakeVectorStore()
    embedder = FakeEmbedder()
    ingest_file(file_id=fid, db=db, embedder=embedder, store=store)
    row = db._conn.execute(
        "SELECT status, error_message FROM materia_files WHERE id = ?", (fid,)
    ).fetchone()
    assert row[0] == "error"
    assert row[1]


def test_reindex_transcript_writes_chunks(db: HistoryDB) -> None:
    cid = _seed_collection(db)
    db.record(
        source_path="/v/l.mp4",
        prefix="T",
        naming_mode="sequential",
        sequential_number=1,
        output_title="Lec",
        output_mode="markdown",
        output_path="/o/L.md",
        language="es",
    )
    vid = db._conn.execute("SELECT id FROM processed_videos").fetchone()[0]
    db.index_transcript(vid, "Lec", "/v/l.mp4", "Uno.\n\nDos.\n\nTres.")

    store = FakeVectorStore()
    reindex_transcript(video_id=vid, collection_id=cid, db=db, embedder=FakeEmbedder(), store=store)
    assert len(store._items) >= 3
    assert all(c.source_type == "transcript" for c in store._items)
    assert all(c.collection_id == cid for c in store._items)


def test_reindex_transcript_overwrites_old_chunks(db: HistoryDB) -> None:
    cid = _seed_collection(db)
    db.record(
        source_path="/v/l.mp4",
        prefix="T",
        naming_mode="sequential",
        sequential_number=1,
        output_title="Lec",
        output_mode="markdown",
        output_path="/o/L.md",
        language="es",
    )
    vid = db._conn.execute("SELECT id FROM processed_videos").fetchone()[0]
    db.index_transcript(vid, "Lec", "/v/l.mp4", "Uno.\n\nDos.")

    store = FakeVectorStore()
    embedder = FakeEmbedder()
    reindex_transcript(video_id=vid, collection_id=cid, db=db, embedder=embedder, store=store)
    n1 = len(store._items)
    # Re-run with the same content; count must stay the same.
    reindex_transcript(video_id=vid, collection_id=cid, db=db, embedder=embedder, store=store)
    assert len(store._items) == n1
