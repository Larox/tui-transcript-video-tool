"""File upload API routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from tui_transcript.api.schemas import UploadedFile, UploadResponse
from tui_transcript.api.state import _get_upload_dir, store_upload

router = APIRouter(prefix="/files", tags=["files"])

ALLOWED_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv",
    ".m4a", ".mp3", ".wav", ".ogg", ".flac",
}


def _is_allowed(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


@router.post("/upload", response_model=UploadResponse)
async def upload_files(files: list[UploadFile] = File(...)) -> UploadResponse:
    """Upload video/audio files for transcription."""
    if not files:
        raise HTTPException(400, "No files provided")

    upload_dir = _get_upload_dir()
    result: list[UploadedFile] = []

    for f in files:
        if not f.filename or not _is_allowed(f.filename):
            raise HTTPException(400, f"Invalid or unsupported file: {f.filename}")

        # Save to temp dir with unique name (preserve extension)
        ext = Path(f.filename).suffix
        dest = upload_dir / f"{f.filename}"
        # Handle duplicates
        counter = 1
        while dest.exists():
            dest = upload_dir / f"{Path(f.filename).stem}_{counter}{ext}"
            counter += 1

        content = await f.read()
        dest.write_bytes(content)

        fid = store_upload(dest, f.filename)
        result.append(UploadedFile(
            id=fid,
            name=f.filename,
            size_bytes=len(content),
        ))

    return UploadResponse(files=result)
