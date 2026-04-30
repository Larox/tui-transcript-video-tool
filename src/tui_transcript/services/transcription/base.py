"""Transcriber Protocol and shared error type."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

from tui_transcript.models import TranscriptResult


class TranscriberError(Exception):
    """Raised when a transcriber cannot run (bad config, missing model, etc.)."""


class Transcriber(Protocol):
    """Common interface for transcription engines."""

    async def transcribe(
        self,
        file_path: Path,
        *,
        language: str,
        on_status: Callable[[str], None] | None = None,
    ) -> TranscriptResult:
        ...
