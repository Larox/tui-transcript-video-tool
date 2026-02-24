"""Pydantic schemas for API request/response."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConfigResponse(BaseModel):
    """Config for GET. API key is masked."""

    deepgram_api_key: str = ""  # Masked as "***" when set
    google_service_account_json: str = ""
    drive_folder_id: str = ""
    naming_mode: str = "sequential"
    prefix: str = "Transcripcion"
    markdown_output_dir: str = "./output"
    output_mode: str = "markdown"


class ConfigUpdate(BaseModel):
    """Partial config update for PUT."""

    deepgram_api_key: str | None = None
    google_service_account_json: str | None = None
    drive_folder_id: str | None = None
    naming_mode: str | None = None
    prefix: str | None = None
    markdown_output_dir: str | None = None


class UploadedFile(BaseModel):
    """Response for a single uploaded file."""

    id: str
    name: str
    size_bytes: int


class UploadResponse(BaseModel):
    """Response after file upload."""

    files: list[UploadedFile]


class FileSpec(BaseModel):
    """File + language for transcription start."""

    id: str
    language: str = "es"


class TranscriptionStartRequest(BaseModel):
    """Request to start transcription."""

    files: list[FileSpec] = Field(..., min_length=1)


class TranscriptionStartResponse(BaseModel):
    """Response with session ID for progress stream."""

    session_id: str


class JobStatusEvent(BaseModel):
    """SSE event: job status changed."""

    type: str = "job_status"
    job: dict


class LogEvent(BaseModel):
    """SSE event: log message."""

    type: str = "log"
    message: str
    level: str = "info"


class ProgressEvent(BaseModel):
    """SSE event: progress advance."""

    type: str = "progress"
    steps: int = 1


class StatusLabelEvent(BaseModel):
    """SSE event: status label update."""

    type: str = "status_label"
    label: str


class DoneEvent(BaseModel):
    """SSE event: pipeline complete."""

    type: str = "done"
