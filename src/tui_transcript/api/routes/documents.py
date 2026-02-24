"""API routes for the document storage / output-directory registry."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from tui_transcript.api.schemas import (
    DirectoryCreate,
    DirectoryEntry,
    DirectoryUpdate,
    DocumentFile,
)
from tui_transcript.services.document_store import (
    DirectoryNotFoundError,
    DocumentStore,
)

router = APIRouter(prefix="/documents", tags=["documents"])


def _store() -> DocumentStore:
    return DocumentStore()


# ------------------------------------------------------------------
# Directory CRUD
# ------------------------------------------------------------------


@router.get("/directories", response_model=list[DirectoryEntry])
def list_directories() -> list[DirectoryEntry]:
    store = _store()
    try:
        return [DirectoryEntry(**d) for d in store.list_directories()]
    finally:
        store.close()


@router.post("/directories", response_model=DirectoryEntry, status_code=201)
def create_directory(body: DirectoryCreate) -> DirectoryEntry:
    store = _store()
    try:
        entry = store.register_directory(body.name, body.path)
        return DirectoryEntry(**entry)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    finally:
        store.close()


@router.put("/directories/{dir_id}", response_model=DirectoryEntry)
def update_directory(dir_id: int, body: DirectoryUpdate) -> DirectoryEntry:
    store = _store()
    try:
        entry = store.reattach_directory(dir_id, body.path)
        return DirectoryEntry(**entry)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    finally:
        store.close()


@router.delete("/directories/{dir_id}")
def delete_directory(dir_id: int) -> dict:
    store = _store()
    try:
        if not store.remove_directory(dir_id):
            raise HTTPException(404, f"Directory id {dir_id} not found")
        return {"ok": True}
    finally:
        store.close()


# ------------------------------------------------------------------
# Files inside a directory
# ------------------------------------------------------------------


@router.get(
    "/directories/{dir_id}/files", response_model=list[DocumentFile]
)
def list_files(dir_id: int) -> list[DocumentFile]:
    store = _store()
    try:
        return [DocumentFile(**f) for f in store.list_files(dir_id)]
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except DirectoryNotFoundError as exc:
        raise HTTPException(422, str(exc))
    finally:
        store.close()


@router.post("/directories/{dir_id}/open")
def open_directory(dir_id: int) -> dict:
    """Open the directory in the OS file manager."""
    from tui_transcript.api.routes.paths import _open_in_file_manager
    from pathlib import Path
    import subprocess

    store = _store()
    try:
        entry = store._db.get_directory(dir_id)
        if entry is None:
            raise HTTPException(404, f"Directory id {dir_id} not found")
        p = Path(entry["path"])
        if not p.is_dir():
            raise HTTPException(
                422,
                f"Directory not found at: {entry['path']}. Please re-attach.",
            )
        _open_in_file_manager(p)
        return {"ok": True}
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise HTTPException(500, f"Failed to open: {exc}")
    finally:
        store.close()
