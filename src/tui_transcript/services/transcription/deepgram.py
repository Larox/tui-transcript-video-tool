"""Deepgram-backed transcriber."""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from deepgram import AsyncDeepgramClient

from tui_transcript.models import TranscriptParagraph, TranscriptResult

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".opus", ".wma"}


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _extract_audio(video_path: Path, out_path: Path) -> None:
    """Use ffmpeg to extract a mono 16 kHz WAV — optimal for Deepgram + Whisper."""
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


def _is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


class DeepgramTranscriber:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

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

        use_ffmpeg = not _is_audio_file(file_path) and _has_ffmpeg()
        tmp_dir = None

        try:
            if use_ffmpeg:
                _notify("Extracting audio track (ffmpeg)...")
                tmp_dir = tempfile.mkdtemp(prefix="tui_transcript_")
                wav_path = Path(tmp_dir) / "audio.wav"
                await asyncio.to_thread(_extract_audio, file_path, wav_path)
                source_path = wav_path
                _notify(
                    f"Audio extracted: {wav_path.stat().st_size / 1_048_576:.1f} MB"
                )
            else:
                source_path = file_path
                size_mb = file_path.stat().st_size / 1_048_576
                if use_ffmpeg is False and not _is_audio_file(file_path):
                    _notify(
                        f"ffmpeg not found — sending raw video ({size_mb:.0f} MB). "
                        "Install ffmpeg for faster uploads."
                    )
                else:
                    _notify(f"Sending audio file ({size_mb:.1f} MB)...")

            _notify("Uploading to Deepgram...")
            audio_bytes = await asyncio.to_thread(source_path.read_bytes)

            client = AsyncDeepgramClient(api_key=self._api_key)
            response = await client.listen.v1.media.transcribe_file(
                request=audio_bytes,
                model="nova-3",
                language=language,
                smart_format=True,
                paragraphs=True,
                diarize=True,
                request_options={"timeout_in_seconds": 600},
            )

            alt = response.results.channels[0].alternatives[0]

            paragraphs: list[TranscriptParagraph] = []
            if alt.paragraphs and alt.paragraphs.paragraphs:
                for para in alt.paragraphs.paragraphs:
                    sentence_texts = [s.text for s in (para.sentences or [])]
                    paragraphs.append(
                        TranscriptParagraph(
                            start=para.start,
                            end=para.end,
                            text=" ".join(sentence_texts),
                        )
                    )

            if alt.paragraphs and alt.paragraphs.transcript:
                return TranscriptResult(
                    text=alt.paragraphs.transcript, paragraphs=paragraphs
                )

            return TranscriptResult(text=alt.transcript or "", paragraphs=paragraphs)

        finally:
            if tmp_dir is not None:
                await asyncio.to_thread(shutil.rmtree, tmp_dir, True)
