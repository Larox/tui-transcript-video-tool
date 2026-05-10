"""Pydantic schemas for API request/response."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ConfigResponse(BaseModel):
    """Config for GET. API key is masked.

    Note: markdown_output_dir and course_name are no longer surfaced —
    output destination is chosen per-batch via the directories registry.
    """

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
    """File + language + engine for transcription start."""

    id: str
    language: str = "es"
    engine: Literal["deepgram", "whisper_local"] = "deepgram"
    whisper_model: Literal["small", "medium", "large-v3"] | None = None
    output_title: str | None = None


class TranscriptionStartRequest(BaseModel):
    """Request to start transcription."""

    files: list[FileSpec] = Field(..., min_length=1)
    directory_id: int | None = Field(
        None, description="ID of the registered output directory; falls back to config default"
    )
    collection_id: int | None = Field(
        None, description="Optional collection (course) to add the resulting videos to"
    )


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
    transcript_count: int = 0
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


# ------------------------------------------------------------------
# Content generation
# ------------------------------------------------------------------


class SummaryResponse(BaseModel):
    """Response for GET /classes/{video_id}/summary."""

    text: str
    generated_at: str


class TranscriptResponse(BaseModel):
    """Response for GET /classes/{video_id}/transcript."""

    text: str


class QAPair(BaseModel):
    """A single question-answer pair."""

    question: str
    answer: str
    starred: bool = False


class QAResponse(BaseModel):
    """Response for GET /classes/{video_id}/qa."""

    pairs: list[QAPair]


class Flashcard(BaseModel):
    """A single concept-definition flashcard."""

    concept: str
    definition: str
    starred: bool = False


class FlashcardsResponse(BaseModel):
    """Response for GET /classes/{video_id}/flashcards."""

    cards: list[Flashcard]


class ActionItem(BaseModel):
    """A single action item."""

    id: int
    text: str
    urgency: str
    extracted_date: str | None
    dismissed: bool


class ActionItemsResponse(BaseModel):
    """Response for GET /classes/{video_id}/action-items."""

    items: list[ActionItem]


class FillInBlankItem(BaseModel):
    """A single fill-in-the-blank item."""

    id: int
    sentence: str
    answer: str
    hint: str = ''
    starred: bool = False


class FillInBlankResponse(BaseModel):
    """Response for GET /classes/{video_id}/fill-in-blank."""

    items: list[FillInBlankItem]


class TrueFalseItem(BaseModel):
    """A single true-or-false statement."""

    id: int
    statement: str
    is_true: bool
    explanation: str = ''
    starred: bool = False


class TrueFalseResponse(BaseModel):
    """Response for GET /classes/{video_id}/true-false."""

    items: list[TrueFalseItem]


class ErrorDetectionItem(BaseModel):
    """A single error-detection item."""

    id: int
    statement: str
    error: str
    correction: str
    explanation: str = ''
    starred: bool = False


class ErrorDetectionResponse(BaseModel):
    """Response for GET /classes/{video_id}/error-detection."""

    items: list[ErrorDetectionItem]


# ------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------


class AlertEntry(BaseModel):
    """An action item in dashboard alerts response (includes video_id and created_at)."""

    id: int
    video_id: int
    text: str
    urgency: str
    extracted_date: str | None
    dismissed: bool
    created_at: str


class AlertsResponse(BaseModel):
    """Response for GET /dashboard/alerts."""

    alerts: list[AlertEntry]


# ------------------------------------------------------------------
# Activity log / stats (SEB-81, SEB-90, refactor/activity-log)
# ------------------------------------------------------------------


class LogActivityRequest(BaseModel):
    """Payload for POST /stats/activity."""

    activity_type: str = Field(..., min_length=1)
    items_done: int = Field(0, ge=0)
    items_correct: int = Field(0, ge=0)


class DailySessionEntry(BaseModel):
    """A single day's aggregated activity data in the summary."""

    date: str
    items_done: int
    items_correct: int


class StatsSummaryResponse(BaseModel):
    """Response for GET /stats/summary."""

    current_streak: int
    longest_streak: int
    total_sessions: int       # distinct days with activity
    total_items_done: int
    total_items_correct: int
    sessions_last_30_days: list[DailySessionEntry]
    daily_goal: int
    today_items: int
    boss_battles_completed: int = 0


# ------------------------------------------------------------------
# Card reviews / Spaced repetition (SEB-86)
# ------------------------------------------------------------------


class CardReviewResponse(BaseModel):
    """Response for updating a card review (after student rates it)."""

    card_id: str
    next_review: str
    ease_factor: float
    interval: int
    repetitions: int


class RateCardRequest(BaseModel):
    """Payload for POST /classes/{video_id}/cards/{card_id}/rate."""

    card_type: str = Field(..., min_length=1)  # 'flashcard', 'quiz', 'fill_in_blank', etc.
    quality: int = Field(..., ge=1, le=5)  # 1-5 rating


# ------------------------------------------------------------------
# Boss Battle (SEB-87)
# ------------------------------------------------------------------


class WeeklyFailingCard(BaseModel):
    """A card that the student got wrong this week."""

    card_id: str
    card_type: str
    fail_count: int
    last_failed_at: str | None = None


class BossBattleResponse(BaseModel):
    """Response for GET /classes/{video_id}/boss-battle."""

    video_id: int
    week_start: str  # ISO date of Monday (start of current week)
    cards: list[WeeklyFailingCard]


# ------------------------------------------------------------------
# RAG: materia files + search
# ------------------------------------------------------------------


class MateriaFileEntry(BaseModel):
    id: int
    collection_id: int
    filename: str
    mime_type: str
    size_bytes: int
    status: str
    error_message: str | None
    uploaded_at: str
    indexed_at: str | None


class RagSearchHit(BaseModel):
    text: str
    score: float
    collection_id: int
    collection_name: str
    source_type: str
    source_label: str
    source_id: str
    page_number: int | None
    chunk_index: int


class RagSearchRequest(BaseModel):
    query: str
    collection_id: int | None = None
    k: int = 8
