"""Verify run_pipeline honors output_dir and course_name overrides."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from tui_transcript.models import (
    AppConfig,
    JobStatus,
    NamingMode,
    TranscriptResult,
    VideoJob,
)
from tui_transcript.services.pipeline import run_pipeline


@pytest.fixture()
def _isolated_history(tmp_path):
    """Force HistoryDB to a temp file so tests don't pollute the real DB."""
    from tui_transcript.services.history import HistoryDB

    orig_init = HistoryDB.__init__
    db_file = tmp_path / "history.db"

    def patched(self, p=db_file):
        orig_init(self, p)

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

    class _FakeTranscriber:
        async def transcribe(self, path, *, language, on_status=None):
            return fake_transcript

    with patch(
        "tui_transcript.services.pipeline.get_transcriber",
        return_value=_FakeTranscriber(),
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


def test_pipeline_falls_back_to_config_course_name_when_override_missing(
    tmp_path, _isolated_history
):
    chosen_dir = tmp_path / "class_beta"
    chosen_dir.mkdir()
    config = AppConfig(
        deepgram_api_key="dg-test",
        naming_mode=NamingMode.SEQUENTIAL,
        prefix="Lec",
        markdown_output_dir=str(tmp_path / "ignored"),
        course_name="From Config",
    )
    job = VideoJob(path=_fake_video(tmp_path), language="en")
    fake_transcript = TranscriptResult(text="hi", paragraphs=[])

    class _FakeTranscriber:
        async def transcribe(self, path, *, language, on_status=None):
            return fake_transcript

    with patch(
        "tui_transcript.services.pipeline.get_transcriber",
        return_value=_FakeTranscriber(),
    ), patch(
        "tui_transcript.services.pipeline.get_media_duration_seconds",
        return_value=60.0,
    ):
        asyncio.run(
            run_pipeline(config, [job], output_dir=chosen_dir, course_name=None)
        )

    body = Path(job.output_path).read_text()
    assert "course_name: From Config" in body


def test_pipeline_falls_back_to_config_output_dir_when_override_missing(
    tmp_path, _isolated_history
):
    fallback_dir = tmp_path / "from_config"
    fallback_dir.mkdir()
    config = AppConfig(
        deepgram_api_key="dg-test",
        naming_mode=NamingMode.SEQUENTIAL,
        prefix="Lec",
        markdown_output_dir=str(fallback_dir),
        course_name="C",
    )
    job = VideoJob(path=_fake_video(tmp_path), language="en")
    fake_transcript = TranscriptResult(text="hi", paragraphs=[])

    class _FakeTranscriber:
        async def transcribe(self, path, *, language, on_status=None):
            return fake_transcript

    with patch(
        "tui_transcript.services.pipeline.get_transcriber",
        return_value=_FakeTranscriber(),
    ), patch(
        "tui_transcript.services.pipeline.get_media_duration_seconds",
        return_value=60.0,
    ):
        asyncio.run(
            run_pipeline(config, [job], output_dir=None, course_name="Override")
        )

    out = Path(job.output_path)
    assert out.parent == fallback_dir
    body = out.read_text()
    assert "course_name: Override" in body


@pytest.mark.asyncio
@pytest.mark.parametrize("engine,model", [("deepgram", None), ("whisper_local", "small")])
async def test_pipeline_dispatches_per_engine(monkeypatch, tmp_path, engine, model):
    """The pipeline must call get_transcriber with the job's engine + model."""
    from tui_transcript.models import (
        AppConfig, JobStatus, NamingMode, TranscriptResult, VideoJob,
    )
    from tui_transcript.services import pipeline as pipeline_mod

    media = tmp_path / "clip.wav"
    media.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")

    job = VideoJob(
        path=media,
        language="en",
        engine=engine,
        whisper_model=model,
    )
    config = AppConfig(
        deepgram_api_key="dg-key",
        anthropic_api_key="",
        prefix="Test",
        naming_mode=NamingMode.ORIGINAL,
    )

    captured = {}

    class FakeTranscriber:
        async def transcribe(self, path, *, language, on_status=None):
            return TranscriptResult(text="hello world", paragraphs=[])

    def fake_get_transcriber(eng, *, model, deepgram_api_key):
        captured["engine"] = eng
        captured["model"] = model
        captured["dg_key"] = deepgram_api_key
        return FakeTranscriber()

    monkeypatch.setattr(pipeline_mod, "get_transcriber", fake_get_transcriber)

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    await pipeline_mod.run_pipeline(
        config, [job], output_dir=out_dir, course_name="Test"
    )

    assert captured["engine"] == engine
    assert captured["model"] == model
    assert job.status == JobStatus.DONE
