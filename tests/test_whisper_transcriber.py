"""Tests for WhisperTranscriber. faster-whisper is mocked."""
from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tui_transcript.models import TranscriptResult


def _seg(start: float, end: float, text: str):
    return SimpleNamespace(start=start, end=end, text=text)


@pytest.fixture
def fake_whisper(monkeypatch):
    """Install a fake faster_whisper module with a controllable WhisperModel."""
    fake = types.ModuleType("faster_whisper")
    instance = MagicMock()
    fake.WhisperModel = MagicMock(return_value=instance)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    # Reset the module-level cache between tests
    from tui_transcript.services.transcription import whisper_local
    whisper_local._MODEL_CACHE.clear()
    return instance


@pytest.mark.asyncio
async def test_transcribe_returns_transcript_result(fake_whisper, tmp_path):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"\x00" * 1024)
    segments = iter(
        [
            _seg(0.0, 1.0, "hello"),
            _seg(1.0, 2.0, "world"),
        ]
    )
    info = SimpleNamespace(duration=2.0, language="en")
    fake_whisper.transcribe.return_value = (segments, info)

    from tui_transcript.services.transcription.whisper_local import WhisperTranscriber

    result = await WhisperTranscriber("small").transcribe(audio, language="en")
    assert isinstance(result, TranscriptResult)
    assert result.text == "hello world"
    assert len(result.paragraphs) == 1
    assert result.paragraphs[0].start == 0.0
    assert result.paragraphs[0].end == 2.0


@pytest.mark.asyncio
async def test_transcribe_passes_none_for_multi_language(fake_whisper, tmp_path):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"\x00")
    fake_whisper.transcribe.return_value = (
        iter([]),
        SimpleNamespace(duration=0.0, language="en"),
    )

    from tui_transcript.services.transcription.whisper_local import WhisperTranscriber

    await WhisperTranscriber("small").transcribe(audio, language="multi")
    _, kwargs = fake_whisper.transcribe.call_args
    assert kwargs["language"] is None


@pytest.mark.asyncio
async def test_transcribe_passes_language_through(fake_whisper, tmp_path):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"\x00")
    fake_whisper.transcribe.return_value = (
        iter([]),
        SimpleNamespace(duration=0.0, language="es"),
    )

    from tui_transcript.services.transcription.whisper_local import WhisperTranscriber

    await WhisperTranscriber("small").transcribe(audio, language="es")
    _, kwargs = fake_whisper.transcribe.call_args
    assert kwargs["language"] == "es"


@pytest.mark.asyncio
async def test_paragraph_split_on_silence_gap(fake_whisper, tmp_path):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"\x00")
    # Two segments with a 2.0s gap should produce two paragraphs (threshold 1.5s).
    segments = iter(
        [
            _seg(0.0, 1.0, "first"),
            _seg(3.0, 4.0, "second"),
        ]
    )
    fake_whisper.transcribe.return_value = (
        segments,
        SimpleNamespace(duration=4.0, language="en"),
    )

    from tui_transcript.services.transcription.whisper_local import WhisperTranscriber

    result = await WhisperTranscriber("small").transcribe(audio, language="en")
    assert len(result.paragraphs) == 2
    assert result.paragraphs[0].text == "first"
    assert result.paragraphs[1].text == "second"


@pytest.mark.asyncio
async def test_paragraph_split_on_segment_count(fake_whisper, tmp_path):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"\x00")
    # Ten consecutive close segments → must split (cap at 8 per paragraph).
    segments = iter([_seg(float(i) * 0.5, float(i) * 0.5 + 0.4, f"s{i}") for i in range(10)])
    fake_whisper.transcribe.return_value = (
        segments,
        SimpleNamespace(duration=10.0, language="en"),
    )

    from tui_transcript.services.transcription.whisper_local import WhisperTranscriber

    result = await WhisperTranscriber("small").transcribe(audio, language="en")
    assert len(result.paragraphs) == 2  # 8 + 2


@pytest.mark.asyncio
async def test_progress_callback_emits_status(fake_whisper, tmp_path):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"\x00")
    segments = iter([_seg(0.0, 1.0, "x"), _seg(1.0, 2.0, "y")])
    fake_whisper.transcribe.return_value = (
        segments,
        SimpleNamespace(duration=2.0, language="en"),
    )

    from tui_transcript.services.transcription.whisper_local import WhisperTranscriber

    statuses: list[str] = []
    await WhisperTranscriber("small").transcribe(
        audio, language="en", on_status=statuses.append
    )
    assert any("Whisper" in s or "model" in s.lower() for s in statuses)
    # Progress messages with timestamp markers were emitted:
    assert any("/" in s for s in statuses)


@pytest.mark.asyncio
async def test_model_cache_reuses_loaded_instance(fake_whisper, tmp_path):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"\x00")
    fake_whisper.transcribe.return_value = (
        iter([]),
        SimpleNamespace(duration=0.0, language="en"),
    )

    from tui_transcript.services.transcription import whisper_local
    from tui_transcript.services.transcription.whisper_local import WhisperTranscriber

    await WhisperTranscriber("small").transcribe(audio, language="en")
    fake_whisper.transcribe.return_value = (
        iter([]),
        SimpleNamespace(duration=0.0, language="en"),
    )
    await WhisperTranscriber("small").transcribe(audio, language="en")

    # Class constructor should be called only once for "small"
    import faster_whisper
    assert faster_whisper.WhisperModel.call_count == 1
    assert "small" in whisper_local._MODEL_CACHE
