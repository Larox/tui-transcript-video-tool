"""High-level service for managing registered output directories and their files."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tui_transcript.services.history import HistoryDB


class DirectoryNotFoundError(Exception):
    """Raised when a registered directory no longer exists on disk."""

    def __init__(self, dir_id: int, path: str) -> None:
        self.dir_id = dir_id
        self.path = path
        super().__init__(
            f"Directory not found at: {path}. Please re-attach."
        )


class DocumentStore:
    """Combines HistoryDB directory registry with filesystem operations."""

    def __init__(self, db: HistoryDB | None = None) -> None:
        self._db = db or HistoryDB()
        self._owns_db = db is None

    # ------------------------------------------------------------------
    # Directory operations
    # ------------------------------------------------------------------

    def list_directories(self) -> list[dict]:
        """Return all registered directories annotated with ``exists`` and ``file_count``."""
        dirs = self._db.list_directories()
        for d in dirs:
            p = Path(d["path"])
            d["exists"] = p.is_dir()
            d["file_count"] = (
                len([f for f in p.iterdir() if f.suffix == ".md"])
                if d["exists"]
                else 0
            )
        return dirs

    def register_directory(self, name: str, path: str) -> dict:
        """Validate *path* exists on disk and register it.

        Returns the directory entry dict.  Raises ``ValueError`` if the path
        is not a directory, or returns the existing entry when already
        registered.
        """
        resolved = str(Path(path).expanduser().resolve())
        p = Path(resolved)
        if not p.is_dir():
            raise ValueError(f"Path is not a directory: {resolved}")
        dir_id = self._db.register_directory(name, resolved)
        entry = self._db.get_directory(dir_id)
        assert entry is not None
        entry["exists"] = True
        entry["file_count"] = len([f for f in p.iterdir() if f.suffix == ".md"])
        return entry

    def reattach_directory(self, dir_id: int, new_path: str) -> dict:
        """Update the filesystem path for an existing directory entry."""
        resolved = str(Path(new_path).expanduser().resolve())
        if not Path(resolved).is_dir():
            raise ValueError(f"Path is not a directory: {resolved}")
        if not self._db.update_directory_path(dir_id, resolved):
            raise KeyError(f"Directory id {dir_id} not found")
        entry = self._db.get_directory(dir_id)
        assert entry is not None
        p = Path(entry["path"])
        entry["exists"] = p.is_dir()
        entry["file_count"] = (
            len([f for f in p.iterdir() if f.suffix == ".md"])
            if entry["exists"]
            else 0
        )
        return entry

    def remove_directory(self, dir_id: int) -> bool:
        """Unregister a directory (does NOT delete files on disk)."""
        return self._db.unregister_directory(dir_id)

    # ------------------------------------------------------------------
    # File listing
    # ------------------------------------------------------------------

    def list_files(self, dir_id: int) -> list[dict]:
        """Return ``.md`` files inside the registered directory.

        Raises ``DirectoryNotFoundError`` when the path no longer exists.
        """
        entry = self._db.get_directory(dir_id)
        if entry is None:
            raise KeyError(f"Directory id {dir_id} not found")
        p = Path(entry["path"])
        if not p.is_dir():
            raise DirectoryNotFoundError(dir_id, entry["path"])
        files: list[dict] = []
        for f in sorted(p.iterdir(), key=lambda x: x.name):
            if f.suffix != ".md":
                continue
            stat = f.stat()
            ref = self._db.get_highlights_ref_for_path(str(f))
            files.append(
                {
                    "name": f.name,
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                    "highlights_id": ref["id"] if ref else None,
                    "highlights_slug": ref["slug"] if ref else None,
                }
            )
        return files

    # ------------------------------------------------------------------
    # Pipeline helper
    # ------------------------------------------------------------------

    def ensure_registered(self, path: str, fallback_name: str = "Output") -> int:
        """Register *path* if not already tracked. Returns the directory id."""
        resolved = str(Path(path).expanduser().resolve())
        return self._db.register_directory(fallback_name, resolved)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        if self._owns_db:
            self._db.close()
