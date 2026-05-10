"""Auto-enqueue reindex on transcript completion + collection attach."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_add_video_to_collection_enqueues_reindex(monkeypatch, tmp_path) -> None:
    from tui_transcript.services.history import HistoryDB
    monkeypatch.setattr("tui_transcript.services.history.DB_PATH", tmp_path / "h.db")
    from tui_transcript.services.rag import background
    from tui_transcript.services.rag.embedder import FakeEmbedder
    from tui_transcript.services.rag.store import FakeVectorStore
    background.shutdown()

    # Seed: collection + a transcribed video.
    db = HistoryDB(tmp_path / "h.db")
    db._conn.execute(
        "INSERT INTO collections (name, collection_type, description, created_at, updated_at) "
        "VALUES ('M', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db.record(
        source_path="/v/x.mp4", prefix="T", naming_mode="sequential",
        sequential_number=1, output_title="Lec", output_mode="markdown",
        output_path="/o/L.md", language="es",
    )
    vid = db._conn.execute("SELECT id FROM processed_videos").fetchone()[0]
    db.index_transcript(vid, "Lec", "/v/x.mp4", "Uno.\n\nDos.")
    db._conn.commit()
    db.close()

    from tui_transcript.api.main import app

    with patch.object(background, "enqueue_reindex_transcript") as enq, \
         TestClient(app) as c:
        # collections.add_items takes a list of video_ids in the body.
        r = c.post("/api/collections/1/items", json={"video_ids": [vid]})
        assert r.status_code in (200, 201)
        enq.assert_called_with(vid, 1)
