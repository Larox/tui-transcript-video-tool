"""Materia files routes + /rag/search."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path):
    # Force HistoryDB and the materia_files storage root into tmp_path.
    from tui_transcript.services.history import HistoryDB
    from tui_transcript.api.routes import materia_files as mf_routes

    db_path = tmp_path / "h.db"
    monkeypatch.setattr(
        "tui_transcript.services.history.DB_PATH", db_path
    )
    monkeypatch.setattr(mf_routes, "STORAGE_ROOT", tmp_path / "files")

    # Use FakeEmbedder + FakeVectorStore for the worker. Patch the start()
    # function so the FastAPI lifespan boots the worker with fakes inside
    # the running event loop (we can't call asyncio.create_task from the
    # main test thread because there's no loop there).
    from tui_transcript.services.rag import background
    from tui_transcript.services.rag.embedder import FakeEmbedder
    from tui_transcript.services.rag.store import FakeVectorStore

    background.shutdown()

    real_start = background.start

    def fake_start(*, db=None, embedder=None, store=None):
        real_start(
            db=db,
            embedder=embedder or FakeEmbedder(),
            store=store or FakeVectorStore(),
        )

    monkeypatch.setattr(background, "start", fake_start)

    # Build app AFTER patches so lifespan picks them up.
    from tui_transcript.api.main import app

    # Seed a collection.
    db = HistoryDB(db_path)
    db._conn.execute(
        "INSERT INTO collections (name, collection_type, description, created_at, updated_at) "
        "VALUES ('M', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    db.close()

    with TestClient(app) as c:
        yield c
    background.shutdown()


def test_upload_lists_then_deletes(client) -> None:
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    with open(pdf, "rb") as fh:
        r = client.post(
            "/api/materias/1/files",
            files={"file": ("two_pages.pdf", fh, "application/pdf")},
        )
    assert r.status_code == 201, r.text
    fid = r.json()["id"]

    listing = client.get("/api/materias/1/files").json()
    assert any(f["id"] == fid for f in listing)

    deleted = client.delete(f"/api/materias/1/files/{fid}")
    assert deleted.status_code == 200

    listing2 = client.get("/api/materias/1/files").json()
    assert all(f["id"] != fid for f in listing2)


def test_rag_search_returns_hits_after_ingest(client) -> None:
    import time
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    with open(pdf, "rb") as fh:
        upload = client.post(
            "/api/materias/1/files",
            files={"file": ("two_pages.pdf", fh, "application/pdf")},
        )
    fid = upload.json()["id"]

    # Drain the worker by polling the file's status until it leaves the
    # pending/extracting/embedding states. The worker runs on the lifespan
    # event loop (in the TestClient's worker thread); calling drain() from
    # this thread would cross loops.
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        listing = client.get("/api/materias/1/files").json()
        match = next((f for f in listing if f["id"] == fid), None)
        if match and match["status"] in ("indexed", "error"):
            break
        time.sleep(0.1)
    assert match is not None and match["status"] == "indexed", match

    r = client.post(
        "/api/rag/search",
        json={"query": "redes neuronales", "collection_id": 1, "k": 4},
    )
    assert r.status_code == 200
    hits = r.json()
    assert len(hits) >= 1
    assert hits[0]["collection_id"] == 1


def test_reindex_endpoint(client) -> None:
    r = client.post("/api/materias/1/reindex")
    assert r.status_code == 202
