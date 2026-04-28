"""Verify markdown_output_dir and course_name are not exposed by the config API."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tui_transcript.api.main import app
from tui_transcript.services.history import HistoryDB


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "cfg.db"
    orig_init = HistoryDB.__init__

    def patched(self, p=db_path):
        orig_init(self, p)

    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-x")
    with patch.object(HistoryDB, "__init__", patched):
        yield TestClient(app)


def test_get_config_does_not_expose_dropped_fields(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    body = res.json()
    assert "markdown_output_dir" not in body
    assert "course_name" not in body
    assert "deepgram_api_key" in body
    assert "naming_mode" in body
    assert "prefix" in body
    assert "anthropic_api_key" in body


def test_put_config_rejects_dropped_fields(client):
    res = client.put("/api/config", json={"markdown_output_dir": "/tmp/x"})
    assert res.status_code == 422

    res = client.put("/api/config", json={"course_name": "X"})
    assert res.status_code == 422


def test_put_config_accepts_surviving_fields(client):
    res = client.put("/api/config", json={"prefix": "Lec"})
    assert res.status_code == 200
