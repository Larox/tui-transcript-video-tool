"""FastAPI application for transcription web API."""

from __future__ import annotations

import uvicorn

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tui_transcript.api.routes import config, files, transcription

app = FastAPI(
    title="TUI Transcript API",
    description="Transcribe video/audio via Deepgram, export to Google Docs or Markdown",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(transcription.router, prefix="/api")


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
