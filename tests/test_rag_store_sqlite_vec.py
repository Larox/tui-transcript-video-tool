"""VectorStore Protocol implementations: FakeVectorStore + SqliteVecStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.embedder import FakeEmbedder
from tui_transcript.services.rag.store import (
    Chunk,
    FakeVectorStore,
    SqliteVecStore,
)


@pytest.fixture()
def store(tmp_path: Path):
    db = HistoryDB(tmp_path / "h.db")
    # Manually insert a collection so FK doesn't bite.
    db._conn.execute(
        "INSERT INTO collections (id, name, collection_type, description, created_at, updated_at) "
        "VALUES (1, 'M', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    s = SqliteVecStore(db=db)
    yield s
    db.close()


def _chunk(idx: int, text: str, vec: list[float]) -> Chunk:
    return Chunk(
        collection_id=1,
        source_type="pdf",
        source_id="42",
        chunk_index=idx,
        text=text,
        page_number=1,
        embedding_model="fake-embedder-v1",
        embedding=vec,
    )


def test_upsert_and_query(store: SqliteVecStore) -> None:
    e = FakeEmbedder()
    chunks = [
        _chunk(i, t, e.embed([t])[0])
        for i, t in enumerate(["redes neuronales", "matrices", "calculo"])
    ]
    store.upsert(chunks)

    qvec = e.embed(["redes neuronales"])[0]
    hits = store.query(
        qvec,
        collection_id=1,
        embedding_model="fake-embedder-v1",
        k=3,
    )
    assert len(hits) == 3
    # The exact-match query should rank first.
    assert hits[0].text == "redes neuronales"
    assert hits[0].score > hits[1].score


def test_upsert_is_idempotent(store: SqliteVecStore) -> None:
    e = FakeEmbedder()
    c = _chunk(0, "x", e.embed(["x"])[0])
    store.upsert([c])
    store.upsert([c])  # second call must not raise nor duplicate
    rows = store._db._conn.execute(
        "SELECT COUNT(*) FROM rag_chunk_meta WHERE source_type='pdf' AND source_id='42'"
    ).fetchone()[0]
    assert rows == 1


def test_delete_removes_meta_and_vector(store: SqliteVecStore) -> None:
    e = FakeEmbedder()
    chunks = [_chunk(i, f"t{i}", e.embed([f"t{i}"])[0]) for i in range(3)]
    store.upsert(chunks)
    store.delete(source_type="pdf", source_id="42", embedding_model="fake-embedder-v1")
    n_meta = store._db._conn.execute(
        "SELECT COUNT(*) FROM rag_chunk_meta WHERE source_id='42'"
    ).fetchone()[0]
    n_vec = store._db._conn.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0]
    assert n_meta == 0
    assert n_vec == 0


def test_query_filters_by_collection(store: SqliteVecStore) -> None:
    # Add a second collection.
    store._db._conn.execute(
        "INSERT INTO collections (id, name, collection_type, description, created_at, updated_at) "
        "VALUES (2, 'Other', 'course', '', '2026-05-09', '2026-05-09')"
    )
    store._db._conn.commit()
    e = FakeEmbedder()
    a = _chunk(0, "alpha", e.embed(["alpha"])[0])
    b = Chunk(
        collection_id=2,
        source_type="pdf",
        source_id="99",
        chunk_index=0,
        text="alpha",
        page_number=1,
        embedding_model="fake-embedder-v1",
        embedding=e.embed(["alpha"])[0],
    )
    store.upsert([a, b])
    hits = store.query(
        e.embed(["alpha"])[0],
        collection_id=1,
        embedding_model="fake-embedder-v1",
        k=10,
    )
    assert all(h.collection_id == 1 for h in hits)


def test_fake_vector_store_roundtrip() -> None:
    s = FakeVectorStore()
    e = FakeEmbedder()
    c = _chunk(0, "t", e.embed(["t"])[0])
    s.upsert([c])
    hits = s.query(e.embed(["t"])[0], collection_id=1, embedding_model="fake-embedder-v1", k=1)
    assert hits[0].text == "t"
    s.delete(source_type="pdf", source_id="42", embedding_model="fake-embedder-v1")
    assert s.query(e.embed(["t"])[0], collection_id=1, embedding_model="fake-embedder-v1", k=1) == []
