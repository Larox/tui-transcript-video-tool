"""API routes for full-text search across transcripts."""

from __future__ import annotations

from fastapi import APIRouter, Query

from tui_transcript.api.schemas import SearchResult, VideoEntry
from tui_transcript.services.collection_store import CollectionStore

router = APIRouter(tags=["search"])


def _store() -> CollectionStore:
    return CollectionStore()


@router.get("/search", response_model=list[SearchResult])
def search_transcripts(
    q: str = Query(..., min_length=1),
    collection_id: int | None = Query(None),
    tag: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[SearchResult]:
    store = _store()
    try:
        results = store.search(
            q, collection_id=collection_id, tag_name=tag, limit=limit
        )
        return [SearchResult(**r) for r in results]
    finally:
        store.close()


@router.get("/videos", response_model=list[VideoEntry])
def list_videos() -> list[VideoEntry]:
    """List all processed videos (for adding to collections)."""
    store = _store()
    try:
        return [VideoEntry(**v) for v in store.list_videos()]
    finally:
        store.close()


@router.get("/videos/{video_id}", response_model=VideoEntry)
def get_video(video_id: int) -> VideoEntry:
    """Return a single processed video by id."""
    from fastapi import HTTPException
    from tui_transcript.services.history import HistoryDB

    db = HistoryDB()
    try:
        video = db.get_video_by_id(video_id)
        if video is None:
            raise HTTPException(404, f"Video id {video_id} not found")
        return VideoEntry(**video)
    finally:
        db.close()
