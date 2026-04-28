"""API routes for tags and video tagging."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from tui_transcript.api.schemas import TagAssign, TagCreate, TagEntry
from tui_transcript.services.collection_store import CollectionStore

router = APIRouter(tags=["tags"])


def _store() -> CollectionStore:
    return CollectionStore()


# ------------------------------------------------------------------
# Tag CRUD
# ------------------------------------------------------------------


@router.get("/tags", response_model=list[TagEntry])
def list_tags() -> list[TagEntry]:
    store = _store()
    try:
        return [TagEntry(**t) for t in store.list_tags()]
    finally:
        store.close()


@router.post("/tags", response_model=TagEntry, status_code=201)
def create_tag(body: TagCreate) -> TagEntry:
    store = _store()
    try:
        t = store.create_tag(body.name, body.color)
        return TagEntry(**t)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        if "UNIQUE" in str(exc):
            raise HTTPException(409, f"Tag '{body.name}' already exists")
        raise
    finally:
        store.close()


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: int) -> dict:
    store = _store()
    try:
        store.delete_tag(tag_id)
        return {"ok": True}
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    finally:
        store.close()


# ------------------------------------------------------------------
# Video tagging
# ------------------------------------------------------------------


@router.get("/videos/{video_id}/tags", response_model=list[TagEntry])
def get_video_tags(video_id: int) -> list[TagEntry]:
    store = _store()
    try:
        return [TagEntry(**t) for t in store.get_video_tags(video_id)]
    finally:
        store.close()


@router.post("/videos/{video_id}/tags", status_code=201)
def add_video_tag(video_id: int, body: TagAssign) -> dict:
    store = _store()
    try:
        store.add_video_tag(video_id, body.tag_id)
        return {"ok": True}
    finally:
        store.close()


@router.delete("/videos/{video_id}/tags/{tag_id}")
def remove_video_tag(video_id: int, tag_id: int) -> dict:
    store = _store()
    try:
        store.remove_video_tag(video_id, tag_id)
        return {"ok": True}
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    finally:
        store.close()
