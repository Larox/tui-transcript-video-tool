"""Single retrieval entry point shared by web app and MCP."""

from __future__ import annotations

from dataclasses import dataclass

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.embedder import Embedder, OpenAIEmbedder
from tui_transcript.services.rag.store import (
    SqliteVecStore,
    StoreHit,
    VectorStore,
)

SCORE_FLOOR = 0.25


@dataclass
class Hit:
    text: str
    score: float
    collection_id: int
    collection_name: str
    source_type: str             # 'pdf' | 'transcript'
    source_label: str            # filename or class title
    source_id: str
    page_number: int | None
    chunk_index: int


def search(
    query: str,
    *,
    collection_id: int | None = None,
    k: int = 8,
    db: HistoryDB | None = None,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
) -> list[Hit]:
    own = db is None
    if own:
        db = HistoryDB()
    embedder = embedder or OpenAIEmbedder()
    store = store or SqliteVecStore(db=db)
    try:
        if not query.strip():
            return []
        qvec = embedder.embed([query])[0]
        raw = store.query(
            qvec,
            collection_id=collection_id,
            embedding_model=embedder.model,
            k=k * 2,
        )
        hits = [_hydrate(h, db) for h in raw if h.score >= SCORE_FLOOR]
        return hits[:k]
    finally:
        if own:
            db.close()


def _hydrate(h: StoreHit, db: HistoryDB) -> Hit:
    name_row = db._conn.execute(
        "SELECT name FROM collections WHERE id = ?", (h.collection_id,)
    ).fetchone()
    collection_name = name_row[0] if name_row else "?"

    if h.source_type == "pdf":
        row = db._conn.execute(
            "SELECT filename FROM materia_files WHERE id = ?", (int(h.source_id),)
        ).fetchone()
        source_label = row[0] if row else h.source_id
    elif h.source_type == "transcript":
        # source_id is "{video_id}-{collection_id}"
        video_id = int(h.source_id.split("-", 1)[0])
        row = db._conn.execute(
            "SELECT output_title FROM processed_videos WHERE id = ?", (video_id,)
        ).fetchone()
        source_label = row[0] if row else h.source_id
    else:
        source_label = h.source_id

    return Hit(
        text=h.text,
        score=h.score,
        collection_id=h.collection_id,
        collection_name=collection_name,
        source_type=h.source_type,
        source_label=source_label,
        source_id=h.source_id,
        page_number=h.page_number,
        chunk_index=h.chunk_index,
    )
