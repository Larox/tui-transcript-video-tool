"""Routes for local Whisper model management."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from tui_transcript.services.transcription import models as local_models

router = APIRouter(prefix="/models/local", tags=["models"])


@router.get("")
def list_local_models() -> list[dict]:
    return local_models.list_models()


def _sse(payload: dict) -> str:
    return f"event: message\ndata: {json.dumps(payload)}\n\n"


@router.post("/{name}/download")
async def download_local_model(name: str) -> StreamingResponse:
    if name not in local_models.LOCAL_MODELS:
        raise HTTPException(404, f"Unknown model: {name}")

    queue: asyncio.Queue = asyncio.Queue()

    async def runner() -> None:
        try:
            def on_progress(pct: int) -> None:
                queue.put_nowait({"type": "progress", "progress": pct})

            await local_models.download(name, on_progress=on_progress)
            queue.put_nowait({"type": "done"})
        except Exception as exc:
            queue.put_nowait({"type": "error", "message": str(exc)})
        finally:
            queue.put_nowait(None)  # sentinel

    asyncio.create_task(runner())

    async def stream():
        while True:
            event = await queue.get()
            if event is None:
                return
            yield _sse(event)
            if event.get("type") in {"done", "error"}:
                return

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/{name}", status_code=204)
async def delete_local_model(name: str) -> None:
    if name not in local_models.LOCAL_MODELS:
        raise HTTPException(404, f"Unknown model: {name}")
    await local_models.remove(name)
