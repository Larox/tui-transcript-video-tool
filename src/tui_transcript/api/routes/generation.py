"""API routes for study-content generation (summary, Q&A, flashcards, action items, fill-in-blank)."""

from __future__ import annotations

import io
import json
import re
import zipfile
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from tui_transcript.api.schemas import (
    ActionItem,
    ActionItemsResponse,
    ErrorDetectionItem,
    ErrorDetectionResponse,
    Flashcard,
    FillInBlankItem,
    FillInBlankResponse,
    FlashcardsResponse,
    QAPair,
    QAResponse,
    SummaryResponse,
    TranscriptResponse,
    TrueFalseItem,
    TrueFalseResponse,
)
from tui_transcript.services import content_generator
from tui_transcript.services.history import HistoryDB
from tui_transcript.services.study_store import StudyStore

router = APIRouter(prefix="/classes", tags=["generation"])


def _store() -> StudyStore:
    return StudyStore()


def _db() -> HistoryDB:
    return HistoryDB()


def _sse_data(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def _generation_stream(
    video_id: int, transcript: str, language: str | None = None
) -> AsyncGenerator[str, None]:
    """Run all 7 generators sequentially, saving each result and streaming progress."""
    store = StudyStore()
    try:
        # --- summary ---
        summary_text = await content_generator.generate_summary(transcript, language)
        store.save_summary(video_id, summary_text)
        yield _sse_data({"type": "progress", "step": "summary", "status": "done"})

        # --- Q&A ---
        qa_pairs = await content_generator.generate_qa_pairs(transcript, language)
        store.save_qa_pairs(video_id, qa_pairs)
        yield _sse_data({"type": "progress", "step": "qa", "status": "done"})

        # --- flashcards ---
        flashcards = await content_generator.generate_flashcards(transcript, language)
        store.save_flashcards(video_id, flashcards)
        yield _sse_data({"type": "progress", "step": "flashcards", "status": "done"})

        # --- action items ---
        action_items = await content_generator.generate_action_items(transcript, language)
        store.save_action_items(video_id, action_items)
        yield _sse_data({"type": "progress", "step": "action_items", "status": "done"})

        # --- fill-in-the-blank ---
        fill_in_blank = await content_generator.generate_fill_in_blank(transcript, language)
        store.save_fill_in_blank(video_id, fill_in_blank)
        yield _sse_data({"type": "progress", "step": "fill_in_blank", "status": "done"})

        # --- true/false ---
        true_false = await content_generator.generate_true_false(transcript, language)
        store.save_true_false(video_id, true_false)
        yield _sse_data({"type": "progress", "step": "true_false", "status": "done"})

        # --- error detection ---
        error_detection = await content_generator.generate_error_detection(transcript, language)
        store.save_error_detection(video_id, error_detection)
        yield _sse_data({"type": "progress", "step": "error_detection", "status": "done"})

        yield _sse_data({"type": "complete"})
    finally:
        store.close()


@router.post("/{video_id}/generate")
async def generate_content(video_id: int, language: str | None = None):
    """Trigger generation of all 4 content types for a video. Streams SSE progress."""
    db = _db()
    try:
        video = db.get_video_by_id(video_id)
        if video is None:
            raise HTTPException(404, f"Video id {video_id} not found")
        transcript = db.get_transcript_content(video_id) or ""
    finally:
        db.close()

    return StreamingResponse(
        _generation_stream(video_id, transcript, language),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{video_id}/transcript", response_model=TranscriptResponse)
def get_transcript(video_id: int) -> TranscriptResponse:
    """Return the full transcript text for a video."""
    db = _db()
    try:
        text = db.get_transcript_content(video_id)
        if text is None:
            raise HTTPException(404, f"No transcript found for video id {video_id}")
        return TranscriptResponse(text=text)
    finally:
        db.close()


def _safe_filename(name: str) -> str:
    """Sanitize *name* for use as a filename."""
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name).strip().strip(".")
    return cleaned or "untitled"


def _transcript_markdown(title: str, processed_at: str | None, text: str) -> str:
    header = f"# {title}\n\n"
    if processed_at:
        header += f"_Transcrito: {processed_at}_\n\n"
    header += "---\n\n"
    return header + text


@router.get("/{video_id}/transcript.md")
def download_transcript_markdown(video_id: int) -> Response:
    """Download the transcript as a markdown file."""
    db = _db()
    try:
        video = db.get_video_by_id(video_id)
        if video is None:
            raise HTTPException(404, f"Video id {video_id} not found")
        text = db.get_transcript_content(video_id)
        if text is None:
            raise HTTPException(404, f"No transcript found for video id {video_id}")
        title = video.get("output_title") or f"clase-{video_id}"
    finally:
        db.close()

    body = _transcript_markdown(title, video.get("processed_at"), text)
    filename = f"{_safe_filename(title)}.md"
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/transcripts/export")
def export_all_transcripts(collection_id: int | None = None) -> Response:
    """Download all processed-video transcripts as a ZIP of markdown files.

    When ``collection_id`` is provided, only export transcripts from videos
    belonging to that collection.
    """
    from tui_transcript.services.collection_store import CollectionStore

    store = CollectionStore()
    db = _db()
    zip_basename = "transcripts"
    try:
        if collection_id is not None:
            try:
                collection = store.get_collection(collection_id)
            except KeyError:
                raise HTTPException(404, f"Collection id {collection_id} not found")
            videos = store.get_collection_with_items(collection_id)["items"]
            zip_basename = _safe_filename(collection["name"]) or "transcripts"
        else:
            videos = store.list_videos()

        buf = io.BytesIO()
        used: set[str] = set()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for v in videos:
                vid = v["id"]
                text = db.get_transcript_content(vid)
                if not text:
                    continue
                title = v.get("output_title") or f"clase-{vid}"
                base = _safe_filename(title)
                name = f"{base}.md"
                # Disambiguate duplicates
                i = 2
                while name in used:
                    name = f"{base}-{i}.md"
                    i += 1
                used.add(name)
                zf.writestr(name, _transcript_markdown(title, v.get("processed_at"), text))
    finally:
        db.close()
        store.close()

    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_basename}.zip"'},
    )


@router.get("/{video_id}/summary", response_model=SummaryResponse)
def get_summary(video_id: int) -> SummaryResponse:
    """Return generated summary for a video."""
    store = _store()
    try:
        row = store.get_summary(video_id)
        if row is None:
            raise HTTPException(404, f"No summary found for video id {video_id}")
        return SummaryResponse(text=row["text"], generated_at=row["generated_at"])
    finally:
        store.close()


@router.get("/{video_id}/qa", response_model=QAResponse)
def get_qa(video_id: int) -> QAResponse:
    """Return generated Q&A pairs for a video."""
    store = _store()
    try:
        pairs = store.get_qa_pairs(video_id)
        return QAResponse(pairs=[QAPair(question=p["question"], answer=p["answer"]) for p in pairs])
    finally:
        store.close()


@router.get("/{video_id}/flashcards", response_model=FlashcardsResponse)
def get_flashcards(video_id: int) -> FlashcardsResponse:
    """Return generated flashcards for a video."""
    store = _store()
    try:
        cards = store.get_flashcards(video_id)
        return FlashcardsResponse(
            cards=[Flashcard(concept=c["concept"], definition=c["definition"]) for c in cards]
        )
    finally:
        store.close()


@router.get("/{video_id}/action-items", response_model=ActionItemsResponse)
def get_action_items(video_id: int) -> ActionItemsResponse:
    """Return action items for a video."""
    store = _store()
    try:
        items = store.get_action_items(video_id)
        return ActionItemsResponse(
            items=[
                ActionItem(
                    id=item["id"],
                    text=item["text"],
                    urgency=item["urgency"],
                    extracted_date=item["extracted_date"],
                    dismissed=item["dismissed"],
                )
                for item in items
            ]
        )
    finally:
        store.close()


@router.patch("/{video_id}/action-items/{item_id}/dismiss")
def dismiss_action_item(video_id: int, item_id: int) -> dict:
    """Dismiss an action item."""
    store = _store()
    try:
        store.dismiss_action_item(item_id)
        return {"ok": True}
    finally:
        store.close()


@router.get("/{video_id}/fill-in-blank", response_model=FillInBlankResponse)
def get_fill_in_blank(video_id: int) -> FillInBlankResponse:
    """Return fill-in-the-blank items for a video."""
    store = _store()
    try:
        items = store.get_fill_in_blank(video_id)
        return FillInBlankResponse(
            items=[
                FillInBlankItem(
                    id=item["id"],
                    sentence=item["sentence"],
                    answer=item["answer"],
                    hint=item["hint"],
                    starred=item["starred"],
                )
                for item in items
            ]
        )
    finally:
        store.close()


@router.get("/{video_id}/true-false", response_model=TrueFalseResponse)
def get_true_false(video_id: int) -> TrueFalseResponse:
    """Return true/false statements for a video."""
    store = _store()
    try:
        items = store.get_true_false(video_id)
        return TrueFalseResponse(
            items=[
                TrueFalseItem(
                    id=item["id"],
                    statement=item["statement"],
                    is_true=item["is_true"],
                    explanation=item["explanation"],
                    starred=item["starred"],
                )
                for item in items
            ]
        )
    finally:
        store.close()


@router.get("/{video_id}/error-detection", response_model=ErrorDetectionResponse)
def get_error_detection(video_id: int) -> ErrorDetectionResponse:
    """Return error-detection items for a video."""
    store = _store()
    try:
        items = store.get_error_detection(video_id)
        return ErrorDetectionResponse(
            items=[
                ErrorDetectionItem(
                    id=item["id"],
                    statement=item["statement"],
                    error=item["error"],
                    correction=item["correction"],
                    explanation=item["explanation"],
                    starred=item["starred"],
                )
                for item in items
            ]
        )
    finally:
        store.close()
