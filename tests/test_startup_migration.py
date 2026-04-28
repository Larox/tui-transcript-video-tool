"""Verify legacy env-based output dir is auto-registered when no directories exist."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tui_transcript.services.history import HistoryDB


@pytest.fixture()
def _tmp_db(tmp_path):
    db_path = tmp_path / "startup.db"
    orig_init = HistoryDB.__init__

    def patched(self, p=db_path):
        orig_init(self, p)

    with patch.object(HistoryDB, "__init__", patched):
        yield db_path


def test_auto_registers_env_dir_when_empty(tmp_path, _tmp_db, monkeypatch):
    legacy = tmp_path / "legacy_output"
    legacy.mkdir()
    monkeypatch.setenv("MARKDOWN_OUTPUT_DIR", str(legacy))
    monkeypatch.setenv("COURSE_NAME", "Old Course")

    from tui_transcript.api.main import auto_register_legacy_output_dir

    auto_register_legacy_output_dir()

    db = HistoryDB()
    try:
        dirs = db.list_directories()
    finally:
        db.close()
    assert len(dirs) == 1
    assert dirs[0]["name"] == "Old Course"
    assert Path(dirs[0]["path"]) == legacy.resolve()


def test_skips_when_directories_already_exist(tmp_path, _tmp_db, monkeypatch):
    existing = tmp_path / "Already"
    existing.mkdir()
    db = HistoryDB()
    try:
        db.register_directory("Already", str(existing.resolve()))
    finally:
        db.close()

    legacy = tmp_path / "legacy"
    legacy.mkdir()
    monkeypatch.setenv("MARKDOWN_OUTPUT_DIR", str(legacy))

    from tui_transcript.api.main import auto_register_legacy_output_dir

    auto_register_legacy_output_dir()

    db = HistoryDB()
    try:
        dirs = db.list_directories()
    finally:
        db.close()
    assert len(dirs) == 1
    assert dirs[0]["name"] == "Already"


def test_skips_when_env_dir_does_not_exist(tmp_path, _tmp_db, monkeypatch):
    monkeypatch.setenv("MARKDOWN_OUTPUT_DIR", str(tmp_path / "nope"))

    from tui_transcript.api.main import auto_register_legacy_output_dir

    auto_register_legacy_output_dir()

    db = HistoryDB()
    try:
        dirs = db.list_directories()
    finally:
        db.close()
    assert dirs == []
