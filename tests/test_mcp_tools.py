"""Pure functions behind the MCP tools."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag import ingest
from tui_transcript.services.rag.embedder import FakeEmbedder
from tui_transcript.services.rag.store import FakeVectorStore
from tui_transcript_mcp.tools import (
    MateriaInfo,
    McpHit,
    list_materias,
    search_knowledge,
    MateriaNotFound,
    AmbiguousMateria,
)


def _seed(db: HistoryDB) -> tuple[int, FakeVectorStore]:
    db._conn.execute(
        "INSERT INTO collections (id, name, collection_type, description, created_at, updated_at) "
        "VALUES (1, 'Redes Neuronales', 'course', 'Curso de DL', '2026-05-09', '2026-05-09')"
    )
    db._conn.execute(
        "INSERT INTO collections (id, name, collection_type, description, created_at, updated_at) "
        "VALUES (2, 'Calculo', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    cur = db._conn.execute(
        "INSERT INTO materia_files "
        "(collection_id, filename, storage_path, mime_type, size_bytes, status, uploaded_at) "
        "VALUES (1, 'Redes.pdf', ?, 'application/pdf', ?, 'pending', ?)",
        (str(pdf), pdf.stat().st_size, datetime.now(timezone.utc).isoformat()),
    )
    db._conn.commit()
    fid = cur.lastrowid
    store = FakeVectorStore()
    embedder = FakeEmbedder()
    ingest.ingest_file(file_id=fid, db=db, embedder=embedder, store=store)
    return fid, store


def test_list_materias_returns_counts(db: HistoryDB) -> None:
    _seed(db)
    materias = list_materias(db=db)
    assert any(m.name == "Redes Neuronales" and m.file_count >= 1 for m in materias)
    assert any(m.name == "Calculo" and m.file_count == 0 for m in materias)


def test_search_knowledge_with_exact_materia(db: HistoryDB) -> None:
    _, store = _seed(db)
    hits = search_knowledge(
        "redes neuronales",
        materia_name="Redes Neuronales",
        db=db,
        embedder=FakeEmbedder(),
        store=store,
    )
    assert len(hits) >= 1
    assert all(isinstance(h, McpHit) for h in hits)
    assert hits[0].materia == "Redes Neuronales"
    assert "Redes.pdf" in hits[0].source


def test_search_knowledge_fuzzy_materia(db: HistoryDB) -> None:
    _, store = _seed(db)
    hits = search_knowledge(
        "redes neuronales",
        materia_name="redes",  # lowercase, partial
        db=db,
        embedder=FakeEmbedder(),
        store=store,
    )
    assert hits[0].materia == "Redes Neuronales"


def test_search_knowledge_unknown_materia_raises(db: HistoryDB) -> None:
    _seed(db)
    with pytest.raises(MateriaNotFound) as exc:
        search_knowledge("x", materia_name="zoology", db=db,
                         embedder=FakeEmbedder(), store=FakeVectorStore())
    assert "zoology" in str(exc.value)


def test_search_knowledge_ambiguous_materia_raises(db: HistoryDB) -> None:
    db._conn.execute(
        "INSERT INTO collections (id, name, collection_type, description, created_at, updated_at) "
        "VALUES (3, 'Redes Sociales', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    _seed(db)
    with pytest.raises(AmbiguousMateria) as exc:
        search_knowledge("x", materia_name="redes", db=db,
                         embedder=FakeEmbedder(), store=FakeVectorStore())
    assert "Redes Neuronales" in str(exc.value)
    assert "Redes Sociales" in str(exc.value)


def test_search_knowledge_no_materia_searches_all(db: HistoryDB) -> None:
    _, store = _seed(db)
    hits = search_knowledge("redes neuronales", db=db,
                            embedder=FakeEmbedder(), store=store)
    assert len(hits) >= 1
