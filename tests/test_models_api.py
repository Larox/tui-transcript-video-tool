"""Tests for the /api/models/local routes."""
from __future__ import annotations

from fastapi.testclient import TestClient

from tui_transcript.api.main import app


def test_list_local_models(monkeypatch):
    fake = [
        {"name": "small", "repo_id": "x/small", "size_mb": 466, "downloaded": True},
        {"name": "medium", "repo_id": "x/medium", "size_mb": 1530, "downloaded": False},
    ]
    from tui_transcript.services.transcription import models as m
    monkeypatch.setattr(m, "list_models", lambda: fake)

    with TestClient(app) as client:
        res = client.get("/api/models/local")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert body[0]["name"] == "small"
    assert body[0]["downloaded"] is True


def test_download_unknown_model_returns_404(monkeypatch):
    with TestClient(app) as client:
        res = client.post("/api/models/local/bogus/download")
    assert res.status_code == 404


def test_download_emits_progress_then_done(monkeypatch):
    from tui_transcript.services.transcription import models as m

    async def fake_download(name, on_progress=None):
        if on_progress:
            on_progress(0)
            on_progress(100)

    monkeypatch.setattr(m, "download", fake_download)

    with TestClient(app) as client:
        with client.stream("POST", "/api/models/local/small/download") as res:
            assert res.status_code == 200
            body = b"".join(res.iter_bytes()).decode()
    assert '"progress": 0' in body
    assert '"progress": 100' in body
    assert '"done"' in body


def test_delete_local_model(monkeypatch):
    called = {}

    async def fake_remove(name):
        called["name"] = name

    from tui_transcript.services.transcription import models as m
    monkeypatch.setattr(m, "remove", fake_remove)

    with TestClient(app) as client:
        res = client.delete("/api/models/local/small")
    assert res.status_code == 204
    assert called == {"name": "small"}


def test_delete_unknown_model_returns_404():
    with TestClient(app) as client:
        res = client.delete("/api/models/local/bogus")
    assert res.status_code == 404
