"""Background ingestion worker."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag import background as bg
from tui_transcript.services.rag.embedder import FakeEmbedder
from tui_transcript.services.rag.store import FakeVectorStore


@pytest.fixture(autouse=True)
def _reset_worker() -> None:
    bg.shutdown()
    yield
    bg.shutdown()


def _seed_collection_and_file(db: HistoryDB, pdf: Path) -> tuple[int, int]:
    db._conn.execute(
        "INSERT INTO collections (name, collection_type, description, created_at, updated_at) "
        "VALUES ('M', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    cid = db._conn.execute("SELECT id FROM collections").fetchone()[0]
    cur = db._conn.execute(
        "INSERT INTO materia_files "
        "(collection_id, filename, storage_path, mime_type, size_bytes, status, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (cid, pdf.name, str(pdf), "application/pdf", pdf.stat().st_size,
         "pending", datetime.now(timezone.utc).isoformat()),
    )
    db._conn.commit()
    return cid, cur.lastrowid


@pytest.mark.asyncio
async def test_worker_processes_enqueued_file(db: HistoryDB) -> None:
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    cid, fid = _seed_collection_and_file(db, pdf)

    store = FakeVectorStore()
    bg.start(db=db, embedder=FakeEmbedder(), store=store)
    bg.enqueue_ingest_file(fid)
    await bg.drain()

    status = db._conn.execute(
        "SELECT status FROM materia_files WHERE id=?", (fid,)
    ).fetchone()[0]
    assert status == "indexed"


@pytest.mark.asyncio
async def test_recover_stuck_jobs_on_start(db: HistoryDB) -> None:
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    cid, fid = _seed_collection_and_file(db, pdf)
    db._conn.execute("UPDATE materia_files SET status='extracting' WHERE id=?", (fid,))
    db._conn.commit()

    store = FakeVectorStore()
    bg.start(db=db, embedder=FakeEmbedder(), store=store)
    await bg.drain()

    status = db._conn.execute(
        "SELECT status FROM materia_files WHERE id=?", (fid,)
    ).fetchone()[0]
    assert status == "indexed"
