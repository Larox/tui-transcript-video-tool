"""Tests for the local Whisper model registry."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tui_transcript.services.transcription import models as m


def test_list_models_returns_all_known_models():
    with patch.object(m, "is_downloaded", return_value=False):
        result = m.list_models()
    names = [info["name"] for info in result]
    assert names == ["small", "medium", "large-v3"]
    assert all(info["downloaded"] is False for info in result)
    assert all(info["size_mb"] > 0 for info in result)


def test_is_downloaded_true_when_repo_in_cache():
    fake_repo = MagicMock(repo_id="Systran/faster-whisper-small")
    fake_cache = MagicMock(repos=[fake_repo])
    with patch.object(m, "scan_cache_dir", return_value=fake_cache):
        assert m.is_downloaded("small") is True


def test_is_downloaded_false_when_repo_missing():
    fake_cache = MagicMock(repos=[])
    with patch.object(m, "scan_cache_dir", return_value=fake_cache):
        assert m.is_downloaded("small") is False


def test_is_downloaded_unknown_model_returns_false():
    assert m.is_downloaded("nonexistent") is False


@pytest.mark.asyncio
async def test_download_calls_snapshot_download(monkeypatch):
    called = {}

    def fake_snapshot(repo_id, **kwargs):
        called["repo_id"] = repo_id
        return "/fake/path"

    monkeypatch.setattr(m, "snapshot_download", fake_snapshot)
    await m.download("small")
    assert called["repo_id"] == "Systran/faster-whisper-small"


@pytest.mark.asyncio
async def test_remove_calls_delete_repo(monkeypatch):
    deleted = {}

    class FakeStrategy:
        def execute(self):
            deleted["executed"] = True

    fake_repo = MagicMock(repo_id="Systran/faster-whisper-small")
    fake_repo.delete.return_value = FakeStrategy()
    fake_cache = MagicMock(repos=[fake_repo])

    monkeypatch.setattr(m, "scan_cache_dir", lambda: fake_cache)
    await m.remove("small")
    assert deleted == {"executed": True}


@pytest.mark.asyncio
async def test_remove_unknown_model_raises():
    with pytest.raises(ValueError):
        await m.remove("nonexistent")
