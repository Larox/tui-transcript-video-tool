"""API routes for path operations (e.g. open in file manager)."""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException

from pydantic import BaseModel

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
