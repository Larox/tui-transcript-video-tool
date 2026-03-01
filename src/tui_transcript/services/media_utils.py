"""Media file utilities (duration, etc.)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def get_media_duration_seconds(path: Path) -> float | None:
    """Get duration of video/audio file via ffprobe.

    Returns duration in seconds, or None if ffprobe is unavailable or fails.
    """
    if shutil.which("ffprobe") is None:
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        raw = (result.stdout or "").strip()
        if not raw:
            return None
        return float(raw)
    except (subprocess.CalledProcessError, ValueError):
        return None
