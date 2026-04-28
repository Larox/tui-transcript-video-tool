"""FastAPI application for transcription web API."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import uvicorn

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tui_transcript.api.routes import (
    collections,
    config,
    documents,
    files,
    paths,
    search,
    tags,
    transcription,
)

logger = logging.getLogger(__name__)


def auto_register_legacy_output_dir() -> None:
    """If no directories are registered yet but MARKDOWN_OUTPUT_DIR is set
    and exists on disk, register it once so existing TUI users don't lose
    their setup when they open the web app.
    """
    from tui_transcript.services.history import HistoryDB

    legacy_path = os.environ.get("MARKDOWN_OUTPUT_DIR", "").strip()
    if not legacy_path:
        return
    p = Path(legacy_path).expanduser().resolve()
    if not p.is_dir():
        return

    db = HistoryDB()
    try:
        if db.list_directories():
            return
        name = os.environ.get("COURSE_NAME", "").strip() or "Default"
        db.register_directory(name, str(p))
        logger.info("Auto-registered legacy output dir %s as '%s'", p, name)
    finally:
        db.close()


app = FastAPI(
    title="TUI Transcript API",
    description="Transcribe video/audio via Deepgram, export to Markdown",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _on_startup() -> None:
    auto_register_legacy_output_dir()


app.include_router(collections.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(transcription.router, prefix="/api")
app.include_router(paths.router, prefix="/api")


@app.get("/")
def root() -> dict:
    """Health check."""
    return {"status": "ok", "message": "TUI Transcript API"}


@app.get("/api/health")
def health() -> dict:
    """API health check."""
    return {"status": "ok"}


def run() -> None:
    """Run the API server."""
    uvicorn.run(
        "tui_transcript.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    run()
