"""Verify RAG schema is created on HistoryDB init."""

from __future__ import annotations

from pathlib import Path

from tui_transcript.services.history import HistoryDB


def test_rag_tables_exist(tmp_path: Path) -> None:
    db = HistoryDB(tmp_path / "h.db")
    try:
        rows = {
            r[0]
            for r in db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','virtual table')"
            )
        }
        # Note: virtual tables show up with type='table' too in sqlite_master.
        for name in ("materia_files", "rag_chunks", "rag_chunk_meta", "embedding_jobs_log"):
            assert name in rows, f"missing table: {name}"
    finally:
        db.close()


def test_rag_chunks_dimension_is_1536(tmp_path: Path) -> None:
    db = HistoryDB(tmp_path / "h.db")
    try:
        # vec0 stores raw float32. Round-trip a 1536-dim vector to confirm the dim.
        import struct
        vec = struct.pack(f"{1536}f", *([0.1] * 1536))
        db._conn.execute("INSERT INTO rag_chunks(rowid, embedding) VALUES (1, ?)", (vec,))
        row = db._conn.execute("SELECT rowid FROM rag_chunks WHERE rowid = 1").fetchone()
        assert row == (1,)
    finally:
        db.close()
