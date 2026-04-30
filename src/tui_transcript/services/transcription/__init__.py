"""Transcription engines. Public API: get_transcriber, Transcriber, TranscriberError."""
from __future__ import annotations

from tui_transcript.services.transcription.base import (
    Transcriber,
    TranscriberError,
)

# Back-compat re-export. Will be replaced in Task 3 when DeepgramTranscriber lands.
from tui_transcript.services._transcription_legacy import transcribe  # noqa: F401

__all__ = ["Transcriber", "TranscriberError", "get_transcriber", "transcribe"]


def get_transcriber(
    engine: str,
    *,
    model: str | None = None,
    deepgram_api_key: str | None = None,
) -> Transcriber:
    """Return a Transcriber for the requested engine.

    engine: "deepgram" | "whisper_local"
    model: required when engine == "whisper_local" (e.g. "large-v3")
    """
    if engine == "deepgram":
        if not deepgram_api_key:
            raise TranscriberError("Deepgram API key is required for engine='deepgram'")
        from tui_transcript.services.transcription.deepgram import DeepgramTranscriber
        return DeepgramTranscriber(deepgram_api_key)
    if engine == "whisper_local":
        if not model:
            raise TranscriberError("model is required for engine='whisper_local'")
        from tui_transcript.services.transcription.whisper_local import (
            WhisperTranscriber,
        )
        return WhisperTranscriber(model)
    raise TranscriberError(f"Unknown engine: {engine}")
