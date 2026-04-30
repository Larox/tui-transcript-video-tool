"""Local Whisper model registry — wraps Hugging Face cache management."""
from __future__ import annotations

import asyncio
from typing import Callable

from huggingface_hub import scan_cache_dir, snapshot_download
from huggingface_hub.errors import CacheNotFound

# name -> (HF repo_id, approx size in MB)
LOCAL_MODELS: dict[str, tuple[str, int]] = {
    "small":    ("Systran/faster-whisper-small",    466),
    "medium":   ("Systran/faster-whisper-medium",   1530),
    "large-v3": ("Systran/faster-whisper-large-v3", 3090),
}


def list_models() -> list[dict]:
    """List all known local models with their download status."""
    return [
        {
            "name": name,
            "repo_id": repo_id,
            "size_mb": size_mb,
            "downloaded": is_downloaded(name),
        }
        for name, (repo_id, size_mb) in LOCAL_MODELS.items()
    ]


def is_downloaded(name: str) -> bool:
    if name not in LOCAL_MODELS:
        return False
    repo_id, _ = LOCAL_MODELS[name]
    try:
        cache = scan_cache_dir()
    except CacheNotFound:
        return False
    return any(r.repo_id == repo_id for r in cache.repos)


async def download(
    name: str,
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """Download model snapshot. Blocks until complete.

    on_progress: invoked with rough percentage (0..100) — best-effort. HF's
    snapshot_download doesn't expose granular progress, so we emit 0 at start
    and 100 at end. UI should show a spinner during the gap.
    """
    if name not in LOCAL_MODELS:
        raise ValueError(f"Unknown model: {name}")
    repo_id, _ = LOCAL_MODELS[name]
    if on_progress:
        on_progress(0)
    await asyncio.to_thread(snapshot_download, repo_id)
    if on_progress:
        on_progress(100)


async def remove(name: str) -> None:
    """Delete model from HF cache."""
    if name not in LOCAL_MODELS:
        raise ValueError(f"Unknown model: {name}")
    repo_id, _ = LOCAL_MODELS[name]

    def _delete() -> None:
        try:
            cache = scan_cache_dir()
        except CacheNotFound:
            return
        for repo in cache.repos:
            if repo.repo_id == repo_id:
                strategy = repo.delete()
                strategy.execute()
                return

    await asyncio.to_thread(_delete)
