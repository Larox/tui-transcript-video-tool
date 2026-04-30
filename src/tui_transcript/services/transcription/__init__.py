"""Transcription engines. Public API: get_transcriber, transcribe, Transcriber, TranscriberError."""
from __future__ import annotations

from tui_transcript.services.transcription.base import (
    Transcriber,
    TranscriberError,
)

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


async def transcribe(api_key: str, file_path, *, language: str = "es", on_status=None):
    """Back-compat shim — delegates to DeepgramTranscriber.

    Existing callers of `from tui_transcript.services.transcription import transcribe`
    keep working. New code should use `get_transcriber()` instead.
    """
    from tui_transcript.services.transcription.deepgram import DeepgramTranscriber
    return await DeepgramTranscriber(api_key).transcribe(
        file_path, language=language, on_status=on_status
    )
