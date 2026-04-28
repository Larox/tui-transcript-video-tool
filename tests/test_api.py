"""Tests for collection/tag/search API endpoints."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tui_transcript.api.main import app
from tui_transcript.services.history import HistoryDB

_original_init = HistoryDB.__init__


@pytest.fixture()
def _tmp_db(tmp_path: Path):
    """Patch HistoryDB to always use a temp database."""
    db_path = tmp_path / "api_test.db"

    def patched_init(self, db_path_arg: Path = db_path):
        _original_init(self, db_path_arg)

    with patch.object(HistoryDB, "__init__", patched_init):
        yield db_path


@pytest.fixture()
def client(_tmp_db) -> TestClient:
    return TestClient(app)


@pytest.fixture()
def db(_tmp_db) -> HistoryDB:
    """Direct DB access for seeding test data."""
    return HistoryDB()


def _seed_video(db: HistoryDB, idx: int = 1) -> int:
    db.record(
        source_path=f"/test/video_{idx}.mp4",
        prefix="T",
        naming_mode="sequential",
        sequential_number=idx,
        output_title=f"Video {idx}",
        output_mode="markdown",
        output_path=f"/out/Video_{idx}.md",
        language="en",
    )
    row = db._conn.execute(
        "SELECT id FROM processed_videos WHERE source_path = ?",
        (f"/test/video_{idx}.mp4",),
    ).fetchone()
    return row[0]


class TestCollectionsAPI:
    def test_list_empty(self, client: TestClient) -> None:
        resp = client.get("/api/collections")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_and_get(self, client: TestClient) -> None:
        resp = client.post(
            "/api/collections",
            json={"name": "ML Course", "collection_type": "course", "description": "test"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "ML Course"
        cid = data["id"]

        resp = client.get(f"/api/collections/{cid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "ML Course"
        assert resp.json()["items"] == []

    def test_create_invalid_type(self, client: TestClient) -> None:
        resp = client.post(
            "/api/collections",
            json={"name": "Bad", "collection_type": "invalid"},
        )
        assert resp.status_code == 422

    def test_update(self, client: TestClient) -> None:
        resp = client.post("/api/collections", json={"name": "Old"})
        cid = resp.json()["id"]

        resp = client.put(f"/api/collections/{cid}", json={"name": "New"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    def test_delete(self, client: TestClient) -> None:
        resp = client.post("/api/collections", json={"name": "Del"})
        cid = resp.json()["id"]

        resp = client.delete(f"/api/collections/{cid}")
        assert resp.status_code == 200

        resp = client.get(f"/api/collections/{cid}")
        assert resp.status_code == 404

    def test_add_and_remove_items(self, client: TestClient, db: HistoryDB) -> None:
        vid = _seed_video(db)
        resp = client.post("/api/collections", json={"name": "C"})
        cid = resp.json()["id"]

        resp = client.post(f"/api/collections/{cid}/items", json={"video_ids": [vid]})
        assert resp.status_code == 201

        resp = client.get(f"/api/collections/{cid}")
        assert len(resp.json()["items"]) == 1

        resp = client.delete(f"/api/collections/{cid}/items/{vid}")
        assert resp.status_code == 200

        resp = client.get(f"/api/collections/{cid}")
        assert len(resp.json()["items"]) == 0


class TestTagsAPI:
    def test_create_and_list(self, client: TestClient) -> None:
        resp = client.post("/api/tags", json={"name": "python", "color": "#3b82f6"})
        assert resp.status_code == 201
        assert resp.json()["name"] == "python"

        resp = client.get("/api/tags")
        assert len(resp.json()) == 1

    def test_delete(self, client: TestClient) -> None:
        resp = client.post("/api/tags", json={"name": "del"})
        tid = resp.json()["id"]

        resp = client.delete(f"/api/tags/{tid}")
        assert resp.status_code == 200
        assert len(client.get("/api/tags").json()) == 0

    def test_video_tagging(self, client: TestClient, db: HistoryDB) -> None:
        vid = _seed_video(db)
        resp = client.post("/api/tags", json={"name": "ml"})
        tid = resp.json()["id"]

        resp = client.post(f"/api/videos/{vid}/tags", json={"tag_id": tid})
        assert resp.status_code == 201

        resp = client.get(f"/api/videos/{vid}/tags")
        assert len(resp.json()) == 1

        resp = client.delete(f"/api/videos/{vid}/tags/{tid}")
        assert resp.status_code == 200


class TestSearchAPI:
    def test_search(self, client: TestClient, db: HistoryDB) -> None:
        vid = _seed_video(db)
        db.index_transcript(vid, "Video 1", "/test/video_1.mp4", "Deep learning fundamentals")

        resp = client.get("/api/search", params={"q": "deep learning"})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["video_id"] == vid

    def test_list_videos(self, client: TestClient, db: HistoryDB) -> None:
        _seed_video(db, 1)
        _seed_video(db, 2)

        resp = client.get("/api/videos")
        assert resp.status_code == 200
        assert len(resp.json()) == 2
