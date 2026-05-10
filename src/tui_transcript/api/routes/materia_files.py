"""HTTP routes for per-materia files + reindex queueing."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from tui_transcript.api.schemas import MateriaFileEntry
from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag import background

router = APIRouter(prefix="/materias", tags=["materia-files"])

STORAGE_ROOT = Path.home() / ".tui_transcript" / "materia_files"


def _db() -> HistoryDB:
    return HistoryDB()


@router.post("/{collection_id}/files", response_model=MateriaFileEntry, status_code=201)
async def upload_file(collection_id: int, file: UploadFile = File(...)) -> MateriaFileEntry:
    db = _db()
    try:
        if db._conn.execute(
            "SELECT 1 FROM collections WHERE id=?", (collection_id,)
        ).fetchone() is None:
            raise HTTPException(404, f"Collection {collection_id} not found")

        STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        materia_dir = STORAGE_ROOT / str(collection_id)
        materia_dir.mkdir(parents=True, exist_ok=True)
        storage_path = materia_dir / f"{uuid.uuid4()}-{file.filename}"
        body = await file.read()
        storage_path.write_bytes(body)

        cur = db._conn.execute(
            "INSERT INTO materia_files "
            "(collection_id, filename, storage_path, mime_type, size_bytes, status, uploaded_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (
                collection_id,
                file.filename,
                str(storage_path),
                file.content_type or "application/octet-stream",
                len(body),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        db._conn.commit()
        fid = cur.lastrowid
        background.enqueue_ingest_file(fid)
        row = db._conn.execute(
            "SELECT id, collection_id, filename, mime_type, size_bytes, status, "
            "error_message, uploaded_at, indexed_at FROM materia_files WHERE id=?",
            (fid,),
        ).fetchone()
        return _row_to_entry(row)
    finally:
        db.close()


@router.get("/{collection_id}/files", response_model=list[MateriaFileEntry])
def list_files(collection_id: int) -> list[MateriaFileEntry]:
    db = _db()
    try:
        rows = db._conn.execute(
            "SELECT id, collection_id, filename, mime_type, size_bytes, status, "
            "error_message, uploaded_at, indexed_at FROM materia_files "
            "WHERE collection_id=? ORDER BY uploaded_at DESC",
            (collection_id,),
        ).fetchall()
        return [_row_to_entry(r) for r in rows]
    finally:
        db.close()


@router.delete("/{collection_id}/files/{file_id}")
def delete_file(collection_id: int, file_id: int) -> dict:
    db = _db()
    try:
        row = db._conn.execute(
            "SELECT storage_path FROM materia_files WHERE id=? AND collection_id=?",
            (file_id, collection_id),
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"File {file_id} not in materia {collection_id}")
        try:
            Path(row[0]).unlink(missing_ok=True)
        except OSError:
            pass
        # Drop chunks too.
        from tui_transcript.services.rag.store import SqliteVecStore
        from tui_transcript.services.rag.embedder import OpenAIEmbedder
        store = SqliteVecStore(db=db)
        store.delete(
            source_type="pdf",
            source_id=str(file_id),
            embedding_model=OpenAIEmbedder.model,
        )
        db._conn.execute("DELETE FROM materia_files WHERE id=?", (file_id,))
        db._conn.commit()
        return {"ok": True}
    finally:
        db.close()


@router.post("/{collection_id}/reindex", status_code=202)
def reindex_materia(collection_id: int) -> dict:
    """Re-enqueue every file in this materia + every transcript already attached."""
    db = _db()
    try:
        for (fid,) in db._conn.execute(
            "SELECT id FROM materia_files WHERE collection_id=?", (collection_id,)
        ).fetchall():
            background.enqueue_ingest_file(fid)
        for (vid,) in db._conn.execute(
            "SELECT video_id FROM collection_items WHERE collection_id=?",
            (collection_id,),
        ).fetchall():
            background.enqueue_reindex_transcript(vid, collection_id)
        return {"ok": True}
    finally:
        db.close()


def _row_to_entry(r) -> MateriaFileEntry:
    return MateriaFileEntry(
        id=r[0],
        collection_id=r[1],
        filename=r[2],
        mime_type=r[3],
        size_bytes=r[4],
        status=r[5],
        error_message=r[6],
        uploaded_at=r[7],
        indexed_at=r[8],
    )
