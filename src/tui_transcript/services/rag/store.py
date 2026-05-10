"""VectorStore Protocol + SqliteVecStore + FakeVectorStore.

Migration boundary: this is the only file that knows `sqlite-vec` exists.
Swapping to Chroma / pgvector / LanceDB later means adding one new class here
that implements `VectorStore` and a one-time backfill script.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Protocol

from tui_transcript.services.history import HistoryDB


@dataclass
class Chunk:
    """One chunk ready to write to the index."""

    collection_id: int
    source_type: str            # 'pdf' | 'transcript'
    source_id: str
    chunk_index: int
    text: str
    page_number: int | None
    embedding_model: str
    embedding: list[float]


@dataclass
class StoreHit:
    """One nearest-neighbour result. Distinct from retrieve.Hit (retrieve adds JOINs)."""

    rowid: int
    score: float                # cosine similarity in [-1, 1]; usually [0, 1]
    collection_id: int
    source_type: str
    source_id: str
    chunk_index: int
    text: str
    page_number: int | None


class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk]) -> None: ...
    def query(
        self,
        embedding: list[float],
        *,
        collection_id: int | None,
        embedding_model: str,
        k: int = 8,
    ) -> list[StoreHit]: ...
    def delete(
        self,
        *,
        source_type: str,
        source_id: str,
        embedding_model: str,
    ) -> None: ...


def _to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


class SqliteVecStore:
    """Backs the `rag_chunks` (vec0 virtual table) + `rag_chunk_meta` pair."""

    def __init__(self, db: HistoryDB | None = None) -> None:
        self._db = db or HistoryDB()

    def upsert(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        conn = self._db._conn
        for c in chunks:
            # Delete-then-insert keeps it idempotent under the UNIQUE constraint.
            row = conn.execute(
                "SELECT rowid FROM rag_chunk_meta WHERE source_type=? AND source_id=? "
                "AND chunk_index=? AND embedding_model=?",
                (c.source_type, c.source_id, c.chunk_index, c.embedding_model),
            ).fetchone()
            if row is not None:
                old_rowid = row[0]
                conn.execute("DELETE FROM rag_chunks WHERE rowid = ?", (old_rowid,))
                conn.execute("DELETE FROM rag_chunk_meta WHERE rowid = ?", (old_rowid,))

            cur = conn.execute(
                "INSERT INTO rag_chunk_meta "
                "(collection_id, source_type, source_id, chunk_index, text, page_number, embedding_model) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    c.collection_id,
                    c.source_type,
                    c.source_id,
                    c.chunk_index,
                    c.text,
                    c.page_number,
                    c.embedding_model,
                ),
            )
            new_rowid = cur.lastrowid
            conn.execute(
                "INSERT INTO rag_chunks(rowid, embedding) VALUES (?, ?)",
                (new_rowid, _to_blob(c.embedding)),
            )
        conn.commit()

    def query(
        self,
        embedding: list[float],
        *,
        collection_id: int | None,
        embedding_model: str,
        k: int = 8,
    ) -> list[StoreHit]:
        conn = self._db._conn
        # vec0 returns `distance` = L2 by default; for normalized vectors L2 and
        # cosine are monotonically related. We approximate cosine similarity as
        # 1 - distance**2 / 2 (correct for unit vectors).
        sql = (
            "SELECT v.rowid, v.distance, m.collection_id, m.source_type, m.source_id, "
            "m.chunk_index, m.text, m.page_number "
            "FROM rag_chunks v "
            "JOIN rag_chunk_meta m ON m.rowid = v.rowid "
            "WHERE v.embedding MATCH ? AND k = ? AND m.embedding_model = ?"
        )
        params: list = [_to_blob(embedding), k, embedding_model]
        if collection_id is not None:
            sql += " AND m.collection_id = ?"
            params.append(collection_id)
        rows = conn.execute(sql, params).fetchall()
        hits: list[StoreHit] = []
        for r in rows:
            distance = float(r[1])
            score = max(0.0, 1.0 - (distance * distance) / 2.0)
            hits.append(
                StoreHit(
                    rowid=r[0],
                    score=score,
                    collection_id=r[2],
                    source_type=r[3],
                    source_id=r[4],
                    chunk_index=r[5],
                    text=r[6],
                    page_number=r[7],
                )
            )
        return hits

    def delete(
        self,
        *,
        source_type: str,
        source_id: str,
        embedding_model: str,
    ) -> None:
        conn = self._db._conn
        rows = conn.execute(
            "SELECT rowid FROM rag_chunk_meta "
            "WHERE source_type=? AND source_id=? AND embedding_model=?",
            (source_type, source_id, embedding_model),
        ).fetchall()
        for (rowid,) in rows:
            conn.execute("DELETE FROM rag_chunks WHERE rowid = ?", (rowid,))
            conn.execute("DELETE FROM rag_chunk_meta WHERE rowid = ?", (rowid,))
        conn.commit()


class FakeVectorStore:
    """In-memory store for tests. Brute-force cosine, no SQLite involvement."""

    def __init__(self) -> None:
        self._items: list[Chunk] = []

    def upsert(self, chunks: list[Chunk]) -> None:
        for c in chunks:
            self._items = [
                x for x in self._items
                if not (
                    x.source_type == c.source_type
                    and x.source_id == c.source_id
                    and x.chunk_index == c.chunk_index
                    and x.embedding_model == c.embedding_model
                )
            ]
            self._items.append(c)

    def query(
        self,
        embedding: list[float],
        *,
        collection_id: int | None,
        embedding_model: str,
        k: int = 8,
    ) -> list[StoreHit]:
        candidates = [
            c for c in self._items
            if c.embedding_model == embedding_model
            and (collection_id is None or c.collection_id == collection_id)
        ]
        scored: list[tuple[float, Chunk]] = []
        for c in candidates:
            dot = sum(a * b for a, b in zip(embedding, c.embedding))
            scored.append((dot, c))
        scored.sort(key=lambda p: p[0], reverse=True)
        out: list[StoreHit] = []
        for rowid, (score, c) in enumerate(scored[:k]):
            out.append(
                StoreHit(
                    rowid=rowid,
                    score=score,
                    collection_id=c.collection_id,
                    source_type=c.source_type,
                    source_id=c.source_id,
                    chunk_index=c.chunk_index,
                    text=c.text,
                    page_number=c.page_number,
                )
            )
        return out

    def delete(
        self,
        *,
        source_type: str,
        source_id: str,
        embedding_model: str,
    ) -> None:
        self._items = [
            c for c in self._items
            if not (
                c.source_type == source_type
                and c.source_id == source_id
                and c.embedding_model == embedding_model
            )
        ]
