"""API routes for collections management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from tui_transcript.api.schemas import (
    CollectionAddItems,
    CollectionCreate,
    CollectionDetail,
    CollectionEntry,
    CollectionItemEntry,
    CollectionReorder,
    CollectionUpdate,
)
from tui_transcript.services.collection_store import CollectionStore

router = APIRouter(prefix="/collections", tags=["collections"])


def _store() -> CollectionStore:
    return CollectionStore()


@router.get("", response_model=list[CollectionEntry])
def list_collections() -> list[CollectionEntry]:
    store = _store()
    try:
        return [CollectionEntry(**c) for c in store.list_collections()]
    finally:
        store.close()


@router.post("", response_model=CollectionEntry, status_code=201)
def create_collection(body: CollectionCreate) -> CollectionEntry:
    store = _store()
    try:
        c = store.create_collection(body.name, body.collection_type, body.description)
        c["item_count"] = 0
        return CollectionEntry(**c)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    finally:
        store.close()


@router.get("/{collection_id}", response_model=CollectionDetail)
def get_collection(collection_id: int) -> CollectionDetail:
    store = _store()
    try:
        c = store.get_collection_with_items(collection_id)
        return CollectionDetail(
            id=c["id"],
            name=c["name"],
            collection_type=c["collection_type"],
            description=c["description"],
            created_at=c["created_at"],
            updated_at=c["updated_at"],
            items=[CollectionItemEntry(**item) for item in c["items"]],
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    finally:
        store.close()


@router.put("/{collection_id}", response_model=CollectionEntry)
def update_collection(collection_id: int, body: CollectionUpdate) -> CollectionEntry:
    store = _store()
    try:
        c = store.update_collection(
            collection_id,
            name=body.name,
            collection_type=body.collection_type,
            description=body.description,
        )
        c["item_count"] = len(store._db.list_collection_items(collection_id))
        return CollectionEntry(**c)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    finally:
        store.close()


@router.delete("/{collection_id}")
def delete_collection(collection_id: int) -> dict:
    store = _store()
    try:
        store.delete_collection(collection_id)
        return {"ok": True}
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    finally:
        store.close()


@router.post("/{collection_id}/items", status_code=201)
def add_items(collection_id: int, body: CollectionAddItems) -> dict:
    store = _store()
    try:
        store.add_items(collection_id, body.video_ids)
        # Enqueue RAG reindex for each newly attached transcript.
        from tui_transcript.services.rag import background as _rag_bg
        for vid in body.video_ids:
            try:
                _rag_bg.enqueue_reindex_transcript(vid, collection_id)
            except RuntimeError:
                # Worker not started (isolated tests without lifespan).
                pass
        return {"ok": True, "added": len(body.video_ids)}
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    finally:
        store.close()


@router.delete("/{collection_id}/items/{video_id}")
def remove_item(collection_id: int, video_id: int) -> dict:
    store = _store()
    try:
        store.remove_item(collection_id, video_id)
        return {"ok": True}
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    finally:
        store.close()


@router.put("/{collection_id}/items/reorder")
def reorder_items(collection_id: int, body: CollectionReorder) -> dict:
    store = _store()
    try:
        store.reorder_items(collection_id, body.video_ids)
        return {"ok": True}
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    finally:
        store.close()
