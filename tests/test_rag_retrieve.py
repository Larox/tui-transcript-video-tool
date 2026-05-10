"""retrieve.search() — used by both /rag/search and the MCP server."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag import ingest
from tui_transcript.services.rag.embedder import FakeEmbedder
from tui_transcript.services.rag.retrieve import Hit, search
from tui_transcript.services.rag.store import FakeVectorStore


def _seed_with_pdf(db: HistoryDB, store: FakeVectorStore, embedder: FakeEmbedder) -> int:
    db._conn.execute(
        "INSERT INTO collections (name, collection_type, description, created_at, updated_at) "
        "VALUES ('Redes', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    cid = db._conn.execute("SELECT id FROM collections").fetchone()[0]
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    cur = db._conn.execute(
        "INSERT INTO materia_files "
        "(collection_id, filename, storage_path, mime_type, size_bytes, status, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (cid, pdf.name, str(pdf), "application/pdf", pdf.stat().st_size,
         datetime.now(timezone.utc).isoformat()),
    )
    db._conn.commit()
    fid = cur.lastrowid
    ingest.ingest_file(file_id=fid, db=db, embedder=embedder, store=store)
    return cid


def test_search_returns_hits_for_known_text(db: HistoryDB) -> None:
    store = FakeVectorStore()
    embedder = FakeEmbedder()
    cid = _seed_with_pdf(db, store, embedder)
    hits = search(
        "redes neuronales",
        db=db,
        embedder=embedder,
        store=store,
    )
    assert len(hits) >= 1
    assert all(isinstance(h, Hit) for h in hits)
    assert any("redes" in h.text.lower() for h in hits)
    assert hits[0].collection_id == cid
    assert hits[0].collection_name == "Redes"
    assert hits[0].source_type == "pdf"


def test_search_filters_by_collection(db: HistoryDB) -> None:
    store = FakeVectorStore()
    embedder = FakeEmbedder()
    cid = _seed_with_pdf(db, store, embedder)
    # Add a second collection with no content; result must still come from cid.
    db._conn.execute(
        "INSERT INTO collections (name, collection_type, description, created_at, updated_at) "
        "VALUES ('Otro', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    other = db._conn.execute(
        "SELECT id FROM collections WHERE name='Otro'"
    ).fetchone()[0]

    none_hits = search("redes neuronales", collection_id=other, db=db, embedder=embedder, store=store)
    assert none_hits == []
    some_hits = search("redes neuronales", collection_id=cid, db=db, embedder=embedder, store=store)
    assert len(some_hits) >= 1


def test_search_drops_low_scores(db: HistoryDB) -> None:
    store = FakeVectorStore()
    embedder = FakeEmbedder()
    _seed_with_pdf(db, store, embedder)
    # FakeEmbedder gives unrelated text a near-orthogonal vector → score < 0.25
    hits = search("totally orthogonal nonsense xyzzy", db=db, embedder=embedder, store=store)
    # We don't assert empty (collisions possible) but no result should exceed the floor.
    assert all(h.score >= 0.25 for h in hits)
