"""Verify the Transcriber Protocol shape."""
from __future__ import annotations

import inspect
from pathlib import Path

from tui_transcript.services.transcription.base import (
    Transcriber,
    TranscriberError,
)
from tui_transcript.models import TranscriptResult


def test_transcriber_protocol_has_transcribe_method():
    assert hasattr(Transcriber, "transcribe")


def test_transcriber_error_is_exception():
    assert issubclass(TranscriberError, Exception)


class _FakeTranscriber:
    async def transcribe(self, file_path, *, language, on_status=None):
        return TranscriptResult(text="hi", paragraphs=[])


def test_concrete_class_satisfies_protocol():
    t: Transcriber = _FakeTranscriber()  # structural typing
    sig = inspect.signature(t.transcribe)
    assert "file_path" in sig.parameters
    assert "language" in sig.parameters
    assert "on_status" in sig.parameters
