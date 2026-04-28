"""Verify the transcription start endpoint requires and uses directory_id."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tui_transcript.api.main import app
from tui_transcript.models import TranscriptResult
from tui_transcript.services.history import HistoryDB

_orig_init = HistoryDB.__init__


@pytest.fixture()
def _tmp_db(tmp_path):
    db_path = tmp_path / "api.db"

    def patched(self, p=db_path):
        _orig_init(self, p)

    with patch.object(HistoryDB, "__init__", patched):
        yield db_path


@pytest.fixture()
def client(_tmp_db, tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    return TestClient(app)


def _register_dir(client: TestClient, tmp_path: Path) -> int:
    target = tmp_path / "Algorithms"
    target.mkdir()
    res = client.post(
        "/api/documents/directories",
        json={"name": "Algorithms", "path": str(target)},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _upload_file(client: TestClient, tmp_path: Path) -> str:
    f = tmp_path / "v.mp4"
    f.write_bytes(b"fake")
    with open(f, "rb") as fh:
        res = client.post(
            "/api/files/upload",
            files=[("files", ("v.mp4", fh, "video/mp4"))],
        )
    assert res.status_code == 200, res.text
    return res.json()["files"][0]["id"]


def test_start_requires_directory_id(client, tmp_path):
    file_id = _upload_file(client, tmp_path)
    res = client.post(
        "/api/transcription/start",
        json={"files": [{"id": file_id, "language": "en"}]},
    )
    assert res.status_code == 422, res.text
    body = res.json()
    assert any("directory_id" in str(err) for err in body.get("detail", []))
