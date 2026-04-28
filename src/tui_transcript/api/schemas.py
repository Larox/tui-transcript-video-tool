"""Pydantic schemas for API request/response."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConfigResponse(BaseModel):
    """Config for GET. API key is masked.

    Note: markdown_output_dir and course_name are no longer surfaced —
    output destination is chosen per-batch via the directories registry.
    """

    model_config = {"extra": "forbid"}

    deepgram_api_key: str = ""  # Masked as "***" when set
    naming_mode: str = "sequential"
    prefix: str = "Transcripcion"
    anthropic_api_key: str = ""  # Masked as "***" when set


class ConfigUpdate(BaseModel):
    """Partial config update for PUT."""

    model_config = {"extra": "forbid"}

    deepgram_api_key: str | None = None
    naming_mode: str | None = None
    prefix: str | None = None
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
    directory_id: int = Field(..., description="ID of the registered output directory (a 'class')")


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


# ------------------------------------------------------------------
# Collections
# ------------------------------------------------------------------


class CollectionCreate(BaseModel):
    """Payload for creating a collection."""

    name: str = Field(..., min_length=1)
    collection_type: str = "other"
    description: str = ""


class CollectionUpdate(BaseModel):
    """Partial update for a collection."""

    name: str | None = None
    collection_type: str | None = None
    description: str | None = None


class CollectionEntry(BaseModel):
    """A collection in list responses."""

    id: int
    name: str
    collection_type: str
    description: str
    item_count: int = 0
    created_at: str
    updated_at: str


class CollectionItemEntry(BaseModel):
    """A video/transcript inside a collection."""

    id: int
    source_path: str
    output_title: str
    output_path: str | None
    language: str | None
    processed_at: str
    position: int
    tags: list[dict] = []


class CollectionDetail(BaseModel):
    """Full collection with its items."""

    id: int
    name: str
    collection_type: str
    description: str
    created_at: str
    updated_at: str
    items: list[CollectionItemEntry] = []


class CollectionAddItems(BaseModel):
    """Add videos to a collection."""

    video_ids: list[int] = Field(..., min_length=1)


class CollectionReorder(BaseModel):
    """Reorder items in a collection."""

    video_ids: list[int] = Field(..., min_length=1)


# ------------------------------------------------------------------
# Tags
# ------------------------------------------------------------------


class TagCreate(BaseModel):
    """Payload for creating a tag."""

    name: str = Field(..., min_length=1)
    color: str = "#6b7280"


class TagEntry(BaseModel):
    """A tag."""

    id: int
    name: str
    color: str


class TagAssign(BaseModel):
    """Assign a tag to a video."""

    tag_id: int


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------


class SearchResult(BaseModel):
    """A single search result."""

    video_id: int
    output_title: str
    source_path: str
    excerpt: str
    rank: float = 0.0


class VideoEntry(BaseModel):
    """A processed video for selection UIs."""

    id: int
    source_path: str
    output_title: str
    output_path: str | None
    language: str | None
    processed_at: str
