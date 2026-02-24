"""API routes for path operations (e.g. open in file manager, browse dirs)."""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from pydantic import BaseModel

from tui_transcript.api.schemas import BrowseEntry, BrowseResponse

router = APIRouter(prefix="/paths", tags=["paths"])


class OpenPathRequest(BaseModel):
    path: str


def _open_in_file_manager(path: Path) -> None:
    """Open the given path in the OS file manager."""
    path = path.resolve()
    if not path.exists():
        raise ValueError(f"Path does not exist: {path}")
    if not path.is_dir():
        path = path.parent

    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", str(path)], check=True)
    elif system == "Windows":
        subprocess.run(["explorer", str(path)], check=True)
    else:
        subprocess.run(["xdg-open", str(path)], check=True)


@router.post("/open")
def open_path(req: OpenPathRequest) -> dict:
    """Open a path in the system file manager. Works when API runs locally."""
    try:
        p = Path(req.path).expanduser().resolve()
        _open_in_file_manager(p)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise HTTPException(500, f"Failed to open: {e}")


@router.post("/pick-directory")
def pick_directory() -> dict:
    """Open the native OS folder-picker dialog and return the selected path.

    Returns ``{"path": "/selected/dir"}`` or ``{"path": null}`` if cancelled.
    """
    system = platform.system()
    selected: str | None = None

    if system == "Darwin":
        result = subprocess.run(
            [
                "osascript", "-e",
                'POSIX path of (choose folder with prompt "Select directory")',
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            selected = result.stdout.strip().rstrip("/")
    elif system == "Windows":
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                    "if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath } else { '' }"
                ),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            selected = result.stdout.strip()
    else:
        for cmd in (
            ["zenity", "--file-selection", "--directory", "--title=Select directory"],
            ["kdialog", "--getexistingdirectory", "."],
        ):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    selected = result.stdout.strip()
                break
            except FileNotFoundError:
                continue

    return {"path": selected}


@router.get("/browse", response_model=BrowseResponse)
def browse_directory(path: str = Query(default="~")) -> BrowseResponse:
    """List subdirectories at *path* for the visual directory picker."""
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        raise HTTPException(422, f"Not a directory: {p}")

    parent = str(p.parent) if p != p.parent else None

    children: list[BrowseEntry] = []
    try:
        for child in sorted(p.iterdir(), key=lambda c: c.name.lower()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            try:
                has_children = any(
                    gc.is_dir() for gc in child.iterdir() if not gc.name.startswith(".")
                )
            except PermissionError:
                has_children = False
            children.append(
                BrowseEntry(name=child.name, path=str(child), has_children=has_children)
            )
    except PermissionError:
        raise HTTPException(403, f"Permission denied: {p}")

    return BrowseResponse(current=str(p), parent=parent, children=children)
