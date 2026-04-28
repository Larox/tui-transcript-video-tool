"""Transcription API routes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from tui_transcript.models import JobStatus, VideoJob
from tui_transcript.services.config_store import EnvConfigStore
from tui_transcript.services.pipeline import LogLevel, run_pipeline

from tui_transcript.api.schemas import (
    TranscriptionStartRequest,
    TranscriptionStartResponse,
    TranscriptionStatusResponse,
)
from tui_transcript.api.state import (
    complete_session,
    create_session,
    get_session,
    get_upload,
    set_session_task,
)

router = APIRouter(prefix="/transcription", tags=["transcription"])


def _sse_message(data: dict) -> str:
    """Format SSE as event: message so EventSource onmessage receives it."""
    return f"event: message\ndata: {json.dumps(data)}\n\n"


async def _run_pipeline_with_sse(
    session_id: str,
    config,
    jobs: list[VideoJob],
    queue: asyncio.Queue,
    output_dir: Path,
    course_name: str,
) -> None:
    """Run pipeline, pushing events to queue."""

    class SSECallbacks:
        def on_log(_, msg: str, level: str = LogLevel.INFO) -> None:
            queue.put_nowait({"type": "log", "message": msg, "level": level})

        def on_job_status_changed(_, job: VideoJob) -> None:
            queue.put_nowait({"type": "job_status", "job": job.to_dict()})

        def on_progress_advance(_, steps: int = 1) -> None:
            queue.put_nowait({"type": "progress", "steps": steps})

        def on_status_label(_, label: str) -> None:
            queue.put_nowait({"type": "status_label", "label": label})

    try:
        await run_pipeline(
            config,
            jobs,
            callbacks=SSECallbacks(),
            output_dir=output_dir,
            course_name=course_name,
        )
    finally:
        queue.put_nowait({"type": "done"})
        complete_session(session_id)


@router.post("/start", response_model=TranscriptionStartResponse)
async def start_transcription(req: TranscriptionStartRequest) -> TranscriptionStartResponse:
    """Start transcription for uploaded files. Returns session_id for progress stream."""
    config = EnvConfigStore().load()
    if not config.deepgram_api_key:
        raise HTTPException(400, "Deepgram API key not configured")

    from tui_transcript.services.history import HistoryDB

    db = HistoryDB()
    try:
        directory = db.get_directory(req.directory_id)
    finally:
        db.close()

    if directory is None:
        raise HTTPException(404, f"Directory id {req.directory_id} not found")

    dir_path = Path(directory["path"])
    if not dir_path.is_dir():
        raise HTTPException(
            422,
            f"Class folder missing at {directory['path']}. Please re-attach in Documents.",
        )

    jobs: list[VideoJob] = []
    for spec in req.files:
        upload = get_upload(spec.id)
        if not upload:
            raise HTTPException(404, f"File not found: {spec.id}")
        job = VideoJob(
            path=upload["path"],
            language=spec.language,
            status=JobStatus.PENDING,
        )
        jobs.append(job)

    queue: asyncio.Queue = asyncio.Queue()
    session_id = create_session(queue, jobs)

    task = asyncio.create_task(
        _run_pipeline_with_sse(
            session_id,
            config,
            jobs,
            queue,
            output_dir=dir_path,
            course_name=directory["name"],
        ),
    )
    set_session_task(session_id, task)

    return TranscriptionStartResponse(session_id=session_id)


async def _progress_stream(session_id: str) -> AsyncGenerator[str, None]:
    """SSE stream of progress events. Uses event: message so EventSource onmessage fires."""
    session = get_session(session_id)
    if not session:
        yield _sse_message({"type": "error", "message": "Session not found"})
        return

    queue = session["queue"]
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=30.0)
            if event["type"] == "done":
                yield _sse_message({"type": "done"})
                return
            yield _sse_message(event)
        except asyncio.TimeoutError:
            yield _sse_message({"type": "ping"})
        except Exception as e:
            yield _sse_message({"type": "error", "message": str(e)})
            return


@router.get("/status/{session_id}", response_model=TranscriptionStatusResponse)
async def get_status(session_id: str) -> TranscriptionStatusResponse:
    """Get current session and job status. Use when SSE drops to recover state."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    jobs = session.get("jobs", [])
    status = session.get("status", "running")
    return TranscriptionStatusResponse(
        status=status,
        jobs=[job.to_dict() for job in jobs],
    )


@router.get("/progress/{session_id}")
async def get_progress(session_id: str):
    """SSE stream of transcription progress."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    return StreamingResponse(
        _progress_stream(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
