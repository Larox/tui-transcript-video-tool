"""Pydantic schemas for API request/response."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConfigResponse(BaseModel):
    """Config for GET. API key is masked."""

    deepgram_api_key: str = ""  # Masked as "***" when set
    naming_mode: str = "sequential"
    prefix: str = "Transcripcion"
    course_name: str = ""
    markdown_output_dir: str = "./output"
    anthropic_api_key: str = ""  # Masked as "***" when set


class ConfigUpdate(BaseModel):
    """Partial config update for PUT."""

    deepgram_api_key: str | None = None
    naming_mode: str | None = None
    prefix: str | None = None
    course_name: str | None = None
    markdown_output_dir: str | None = None
    anthropic_api_key: str | None = None


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


class TranscriptionStatusResponse(BaseModel):
    """Response for GET /transcription/status/{session_id}."""

    status: str  # "running" | "done"
    jobs: list[dict]  # Each job as dict (path, status, output_path, etc.)


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


# ------------------------------------------------------------------
# Document storage
# ------------------------------------------------------------------


class DirectoryEntry(BaseModel):
    """A registered output directory with runtime status."""

    id: int
    name: str
    path: str
    exists: bool
    file_count: int
    created_at: str


class DirectoryCreate(BaseModel):
    """Payload for registering a new output directory."""

    name: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)


class DirectoryUpdate(BaseModel):
    """Payload for re-attaching a directory to a new path."""

    path: str = Field(..., min_length=1)


class KeyMoment(BaseModel):
    """A single key moment with timestamp and description."""

    timestamp: str
    description: str


class HighlightsResponse(BaseModel):
    """Response from GET /documents/highlights/{slug}."""

    id: int
    slug: str
    moments: list[KeyMoment]


class DocumentFile(BaseModel):
    """A single document file inside a registered directory."""

    name: str
    size_bytes: int
    modified_at: str
    highlights_id: int | None = None
    highlights_slug: str | None = None


# ------------------------------------------------------------------
# Filesystem browsing
# ------------------------------------------------------------------


class BrowseEntry(BaseModel):
    """A single subdirectory entry returned by the browse endpoint."""

    name: str
    path: str
    has_children: bool


class BrowseResponse(BaseModel):
    """Response from GET /api/paths/browse."""

    current: str
    parent: str | None
    children: list[BrowseEntry]
