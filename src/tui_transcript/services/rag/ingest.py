"""Ingest pipeline. Each entry point is idempotent."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.chunker import ChunkOut, chunk_sections
from tui_transcript.services.rag.cost import (
    EmbeddingCostError,
    count_tokens,
    enforce_source_cap,
    log_embedding_batch,
)
from tui_transcript.services.rag.embedder import Embedder, OpenAIEmbedder
from tui_transcript.services.rag.extractors import get_extractor
from tui_transcript.services.rag.extractors.transcript import extract_transcript
from tui_transcript.services.rag.store import (
    Chunk,
    SqliteVecStore,
    VectorStore,
)

logger = logging.getLogger(__name__)

EMBED_BATCH = 100


def ingest_file(
    *,
    file_id: int,
    db: HistoryDB | None = None,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
) -> None:
    """Extract → chunk → embed → store one materia_files row."""
    own_db = db is None
    if own_db:
        db = HistoryDB()
    embedder = embedder or OpenAIEmbedder()
    store = store or SqliteVecStore(db=db)
    try:
        row = db._conn.execute(
            "SELECT collection_id, storage_path, mime_type FROM materia_files WHERE id = ?",
            (file_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"materia_files id {file_id} not found")
        collection_id, storage_path, mime_type = row

        try:
            _set_status(db, file_id, "extracting")
            extractor = get_extractor(mime_type)
            if extractor is None:
                raise RuntimeError(f"No extractor for mime type: {mime_type}")
            sections = extractor(Path(storage_path))
            chunks_out = chunk_sections(sections)

            tokens = count_tokens([c.text for c in chunks_out])
            enforce_source_cap(tokens)

            _set_status(db, file_id, "embedding")
            store.delete(
                source_type="pdf",
                source_id=str(file_id),
                embedding_model=embedder.model,
            )
            _embed_and_upsert(
                db=db,
                store=store,
                embedder=embedder,
                source_type="pdf",
                source_id=str(file_id),
                collection_id=collection_id,
                chunks_out=chunks_out,
            )
            db._conn.execute(
                "UPDATE materia_files SET status='indexed', indexed_at=?, error_message=NULL "
                "WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), file_id),
            )
            db._conn.commit()
        except (EmbeddingCostError, Exception) as exc:
            logger.exception("ingest_file failed for file_id=%s", file_id)
            db._conn.execute(
                "UPDATE materia_files SET status='error', error_message=? WHERE id=?",
                (str(exc), file_id),
            )
            db._conn.commit()
    finally:
        if own_db:
            db.close()


def reindex_transcript(
    *,
    video_id: int,
    collection_id: int,
    db: HistoryDB | None = None,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
) -> None:
    """(Re-)embed a video's transcript into the index for one collection.

    Source identity is `(transcript, f"{video_id}-{collection_id}")` so the
    same transcript can live in multiple materias without collisions.
    """
    own_db = db is None
    if own_db:
        db = HistoryDB()
    embedder = embedder or OpenAIEmbedder()
    store = store or SqliteVecStore(db=db)
    try:
        sections = extract_transcript(video_id, db=db)
        if not sections:
            return
        chunks_out = chunk_sections(sections)
        tokens = count_tokens([c.text for c in chunks_out])
        try:
            enforce_source_cap(tokens)
        except EmbeddingCostError as exc:
            logger.warning("Skipping transcript %s: %s", video_id, exc)
            return

        source_id = f"{video_id}-{collection_id}"
        store.delete(
            source_type="transcript",
            source_id=source_id,
            embedding_model=embedder.model,
        )
        _embed_and_upsert(
            db=db,
            store=store,
            embedder=embedder,
            source_type="transcript",
            source_id=source_id,
            collection_id=collection_id,
            chunks_out=chunks_out,
        )
    finally:
        if own_db:
            db.close()


def _embed_and_upsert(
    *,
    db: HistoryDB,
    store: VectorStore,
    embedder: Embedder,
    source_type: str,
    source_id: str,
    collection_id: int,
    chunks_out: list[ChunkOut],
) -> None:
    for batch_start in range(0, len(chunks_out), EMBED_BATCH):
        batch = chunks_out[batch_start : batch_start + EMBED_BATCH]
        texts = [c.text for c in batch]
        t0 = time.perf_counter()
        vectors = embedder.embed(texts)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        log_embedding_batch(
            db=db,
            source_type=source_type,
            source_id=source_id,
            batch_size=len(batch),
            tokens=count_tokens(texts),
            latency_ms=latency_ms,
        )
        store.upsert([
            Chunk(
                collection_id=collection_id,
                source_type=source_type,
                source_id=source_id,
                chunk_index=batch_start + i,
                text=c.text,
                page_number=c.page_number,
                embedding_model=embedder.model,
                embedding=vec,
            )
            for i, (c, vec) in enumerate(zip(batch, vectors))
        ])


def _set_status(db: HistoryDB, file_id: int, status: str) -> None:
    db._conn.execute("UPDATE materia_files SET status=? WHERE id=?", (status, file_id))
    db._conn.commit()
