"""Local Whisper transcriber via faster-whisper."""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from tui_transcript.models import TranscriptParagraph, TranscriptResult
from tui_transcript.services.transcription.base import TranscriberError

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".opus", ".wma"}

# Paragraph aggregation tuning:
PARAGRAPH_GAP_SECONDS = 1.5
PARAGRAPH_MAX_SEGMENTS = 8

# Module-level cache so reloads don't happen per job.
_MODEL_CACHE: dict[str, object] = {}


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def _extract_audio(video_path: Path, out_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(out_path),
        ],
        check=True,
        capture_output=True,
    )


def _load_model(name: str):
    if name in _MODEL_CACHE:
        return _MODEL_CACHE[name]
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriberError(
            "faster-whisper is not installed. Run: uv sync"
        ) from exc
    model = WhisperModel(name, device="auto", compute_type="auto")
    _MODEL_CACHE[name] = model
    return model


def _aggregate(segments) -> list[TranscriptParagraph]:
    """Group segments into paragraphs by silence gap or max-count."""
    paragraphs: list[TranscriptParagraph] = []
    current: list = []

    def flush() -> None:
        if not current:
            return
        paragraphs.append(
            TranscriptParagraph(
                start=current[0].start,
                end=current[-1].end,
                text=" ".join(s.text.strip() for s in current),
            )
        )
        current.clear()

    for seg in segments:
        if current:
            gap = seg.start - current[-1].end
            if gap >= PARAGRAPH_GAP_SECONDS or len(current) >= PARAGRAPH_MAX_SEGMENTS:
                flush()
        current.append(seg)
    flush()
    return paragraphs


class WhisperTranscriber:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name

    async def transcribe(
        self,
        file_path: Path,
        *,
        language: str = "es",
        on_status: Callable[[str], None] | None = None,
    ) -> TranscriptResult:
        def _notify(msg: str) -> None:
            if on_status:
                on_status(msg)

        tmp_dir: str | None = None
        try:
            if not _is_audio_file(file_path):
                if not _has_ffmpeg():
                    raise TranscriberError(
                        "ffmpeg not found — required to extract audio for local Whisper."
                    )
                _notify("Extracting audio track (ffmpeg)...")
                tmp_dir = tempfile.mkdtemp(prefix="tui_transcript_whisper_")
                wav_path = Path(tmp_dir) / "audio.wav"
                await asyncio.to_thread(_extract_audio, file_path, wav_path)
                source_path = wav_path
            else:
                source_path = file_path

            _notify(f"Loading Whisper model '{self._model_name}'...")
            model = await asyncio.to_thread(_load_model, self._model_name)

            whisper_lang = None if language == "multi" else language
            _notify("Running local Whisper transcription...")

            def _run():
                return model.transcribe(
                    str(source_path),
                    language=whisper_lang,
                    vad_filter=True,
                    beam_size=5,
                )

            segments_iter, info = await asyncio.to_thread(_run)

            collected = []
            duration = getattr(info, "duration", 0.0) or 0.0
            for seg in segments_iter:
                collected.append(seg)
                if duration > 0:
                    pct = min(100, int((seg.end / duration) * 100))
                    _notify(f"  {seg.end:.0f}s/{duration:.0f}s ({pct}%)")

            paragraphs = _aggregate(collected)
            full_text = " ".join(p.text for p in paragraphs).strip()
            return TranscriptResult(text=full_text, paragraphs=paragraphs)
        finally:
            if tmp_dir is not None:
                await asyncio.to_thread(shutil.rmtree, tmp_dir, True)
