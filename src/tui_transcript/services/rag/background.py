"""In-process asyncio worker for RAG ingestion.

Single concurrency. The FastAPI app starts this in its lifespan; tests start
it explicitly. On start, every materia_files row stuck in extracting/embedding
is re-enqueued (recovery from crash).
"""

from __future__ import annotations

import asyncio
import logging

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.embedder import Embedder, OpenAIEmbedder
from tui_transcript.services.rag.ingest import ingest_file, reindex_transcript
from tui_transcript.services.rag.store import (
    SqliteVecStore,
    VectorStore,
)

logger = logging.getLogger(__name__)


_queue: asyncio.Queue | None = None
_task: asyncio.Task | None = None
_db: HistoryDB | None = None
_embedder: Embedder | None = None
_store: VectorStore | None = None


def start(
    *,
    db: HistoryDB | None = None,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
) -> None:
    """Start the worker. Idempotent."""
    global _queue, _task, _db, _embedder, _store
    if _task is not None and not _task.done():
        return
    _db = db or HistoryDB()
    _embedder = embedder or OpenAIEmbedder()
    _store = store or SqliteVecStore(db=_db)
    _queue = asyncio.Queue()
    _task = asyncio.create_task(_run())
    _recover_stuck_jobs()


def shutdown() -> None:
    """Stop the worker and drop state. Safe to call multiple times."""
    global _queue, _task, _db, _embedder, _store
    if _task is not None and not _task.done():
        _task.cancel()
    _queue = None
    _task = None
    _db = None
    _embedder = None
    _store = None


def get_components() -> tuple[Embedder | None, VectorStore | None]:
    """Return the (embedder, store) the worker was booted with, or (None, None)
    if the worker is down. Used by HTTP routes that want to reuse the same
    embedding stack as the worker (so tests get fakes for free).
    """
    return _embedder, _store


def enqueue_ingest_file(file_id: int) -> None:
    if _queue is None:
        raise RuntimeError("worker not started")
    _queue.put_nowait(("ingest_file", {"file_id": file_id}))


def enqueue_reindex_transcript(video_id: int, collection_id: int) -> None:
    if _queue is None:
        raise RuntimeError("worker not started")
    _queue.put_nowait(
        ("reindex_transcript", {"video_id": video_id, "collection_id": collection_id})
    )


async def drain() -> None:
    """Block until the queue is empty AND the in-flight job finishes. Test helper."""
    if _queue is None:
        return
    await _queue.join()


async def _run() -> None:
    assert _queue is not None
    while True:
        try:
            kind, kwargs = await _queue.get()
        except asyncio.CancelledError:
            return
        try:
            await asyncio.to_thread(_dispatch, kind, kwargs)
        except Exception:
            logger.exception("background worker job %s failed", kind)
        finally:
            _queue.task_done()


def _dispatch(kind: str, kwargs: dict) -> None:
    if kind == "ingest_file":
        ingest_file(db=_db, embedder=_embedder, store=_store, **kwargs)
    elif kind == "reindex_transcript":
        reindex_transcript(db=_db, embedder=_embedder, store=_store, **kwargs)
    else:
        raise RuntimeError(f"unknown job kind: {kind}")


def _recover_stuck_jobs() -> None:
    assert _db is not None
    rows = _db._conn.execute(
        "SELECT id FROM materia_files WHERE status IN ('extracting', 'embedding')"
    ).fetchall()
    for (file_id,) in rows:
        enqueue_ingest_file(file_id)
