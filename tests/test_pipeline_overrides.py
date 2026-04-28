"""Verify run_pipeline honors output_dir and course_name overrides."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tui_transcript.models import (
    AppConfig,
    JobStatus,
    NamingMode,
    TranscriptResult,
    VideoJob,
)
from tui_transcript.services.pipeline import run_pipeline


_orig_history_init = None


@pytest.fixture()
def _isolated_history(tmp_path):
    """Force HistoryDB to a temp file so tests don't pollute the real DB."""
    from tui_transcript.services.history import HistoryDB

    global _orig_history_init
    if _orig_history_init is None:
        _orig_history_init = HistoryDB.__init__

    db_file = tmp_path / "history.db"

    def patched(self, p=db_file):
        _orig_history_init(self, p)

    with patch.object(HistoryDB, "__init__", patched):
        yield db_file


def _fake_video(tmp_path: Path) -> Path:
    p = tmp_path / "video.mp4"
    p.write_bytes(b"fake")
    return p


def test_pipeline_writes_to_override_dir_with_override_course_name(
    tmp_path, _isolated_history
):
    chosen_dir = tmp_path / "class_alpha"
    chosen_dir.mkdir()
    config = AppConfig(
        deepgram_api_key="dg-test",
        naming_mode=NamingMode.SEQUENTIAL,
        prefix="Lec",
        markdown_output_dir=str(tmp_path / "wrong"),
        course_name="WRONG_COURSE",
    )
    job = VideoJob(path=_fake_video(tmp_path), language="en")

    fake_transcript = TranscriptResult(text="hello world", paragraphs=[])

    with patch(
        "tui_transcript.services.pipeline.transcribe",
        new=AsyncMock(return_value=fake_transcript),
    ), patch(
        "tui_transcript.services.pipeline.get_media_duration_seconds",
        return_value=120.0,
    ):
        asyncio.run(
            run_pipeline(
                config,
                [job],
                output_dir=chosen_dir,
                course_name="Algorithms 101",
            )
        )

    assert job.status == JobStatus.DONE
    assert job.output_path
    out = Path(job.output_path)
    assert out.parent == chosen_dir, f"Output landed in {out.parent}, not {chosen_dir}"
    body = out.read_text()
    assert "course_name: Algorithms 101" in body
    assert "WRONG_COURSE" not in body
