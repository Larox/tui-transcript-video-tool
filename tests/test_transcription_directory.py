"""Verify the transcription start endpoint requires and uses directory_id."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tui_transcript.api.main import app
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


def test_start_unknown_directory_id_returns_404(client, tmp_path):
    file_id = _upload_file(client, tmp_path)
    res = client.post(
        "/api/transcription/start",
        json={
            "files": [{"id": file_id, "language": "en"}],
            "directory_id": 9999,
        },
    )
    assert res.status_code == 404, res.text


def test_start_directory_path_missing_returns_422(client, tmp_path):
    target = tmp_path / "GoneClass"
    target.mkdir()
    reg = client.post(
        "/api/documents/directories",
        json={"name": "GoneClass", "path": str(target)},
    )
    dir_id = reg.json()["id"]
    target.rmdir()

    file_id = _upload_file(client, tmp_path)
    res = client.post(
        "/api/transcription/start",
        json={
            "files": [{"id": file_id, "language": "en"}],
            "directory_id": dir_id,
        },
    )
    assert res.status_code == 422, res.text
    assert "re-attach" in res.text.lower()


def test_start_passes_dir_and_name_to_pipeline(client, tmp_path):
    dir_id = _register_dir(client, tmp_path)
    file_id = _upload_file(client, tmp_path)

    captured = {}

    async def fake_run_pipeline(config, jobs, callbacks=None, output_dir=None, course_name=None):
        captured["output_dir"] = output_dir
        captured["course_name"] = course_name

    with patch(
        "tui_transcript.api.routes.transcription.run_pipeline",
        new=fake_run_pipeline,
    ):
        res = client.post(
            "/api/transcription/start",
            json={
                "files": [{"id": file_id, "language": "en"}],
                "directory_id": dir_id,
            },
        )
        assert res.status_code == 200, res.text

        # Drain the SSE so the background task runs
        sid = res.json()["session_id"]
        with client.stream("GET", f"/api/transcription/progress/{sid}") as s:
            for line in s.iter_lines():
                if "done" in (line or ""):
                    break

    assert captured["output_dir"] == (tmp_path / "Algorithms")
    assert captured["course_name"] == "Algorithms"
