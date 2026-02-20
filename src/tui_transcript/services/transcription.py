from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from deepgram import AsyncDeepgramClient

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".opus", ".wma"}


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _extract_audio(video_path: Path, out_path: Path) -> None:
    """Use ffmpeg to extract a mono 16 kHz WAV — optimal for Deepgram."""
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


async def transcribe(
    api_key: str,
    file_path: Path,
    *,
    language: str = "es",
    on_status: callable | None = None,
) -> str:
    """Transcribe a local video/audio file via Deepgram.

    *language* is a BCP-47 code (e.g. ``"es"``, ``"en"``, ``"multi"``).

    If the input is a video and ffmpeg is available, audio is extracted first
    to dramatically reduce upload size (GB -> MB).

    *on_status* is an optional callback ``(msg: str) -> None`` used to push
    progress messages back to the UI.
    """
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

        client = AsyncDeepgramClient(api_key=api_key)
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

        if alt.paragraphs and alt.paragraphs.transcript:
            return alt.paragraphs.transcript

        return alt.transcript or ""

    finally:
        if tmp_dir is not None:
            await asyncio.to_thread(shutil.rmtree, tmp_dir, True)
