"""Shared transcription + export pipeline. Used by both TUI and web API."""

from __future__ import annotations

import asyncio
import logging
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from tui_transcript.models import (
    AppConfig,
    JobStatus,
    LANGUAGES,
    NamingMode,
    VideoJob,
    build_doc_title,
)
from tui_transcript.services.document_store import DocumentStore
from tui_transcript.services.history import HistoryDB
from tui_transcript.services.media_utils import get_media_duration_seconds
from tui_transcript.services.key_moments import extract_key_moments
from tui_transcript.services.transcription import get_transcriber

logger = logging.getLogger(__name__)


class LogLevel:
    """Log levels for TUI markup. Web can ignore or map to CSS."""

    INFO = "info"
    HIGHLIGHT = "highlight"  # cyan/magenta for key actions
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    DIM = "dim"


class PipelineCallbacks(Protocol):
    """Callbacks for pipeline progress. Implement for TUI or web."""

    def on_log(self, msg: str, level: str = LogLevel.INFO) -> None: ...
    def on_job_status_changed(self, job: VideoJob) -> None: ...
    def on_progress_advance(self, steps: int = 1) -> None: ...
    def on_status_label(self, label: str) -> None: ...


@dataclass
class DefaultPipelineCallbacks:
    """No-op callbacks when none provided."""

    def on_log(self, msg: str, level: str = LogLevel.INFO) -> None:
        logger.info(msg)

    def on_job_status_changed(self, job: VideoJob) -> None:
        pass

    def on_progress_advance(self, steps: int = 1) -> None:
        pass

    def on_status_label(self, label: str) -> None:
        pass


async def run_pipeline(
    config: AppConfig,
    jobs: list[VideoJob],
    callbacks: PipelineCallbacks | None = None,
    output_dir: Path | None = None,
    course_name: str | None = None,
) -> None:
    """Run the transcription + export pipeline for pending jobs.

    Mutates jobs in place. Callbacks are invoked for progress, logs, and status.

    When ``output_dir`` is provided, transcripts are written there instead of
    ``config.markdown_output_dir``. When ``course_name`` is provided it overrides
    ``config.course_name`` for the markdown frontmatter.
    """
    cb = callbacks or DefaultPipelineCallbacks()
    pending = [j for j in jobs if j.status == JobStatus.PENDING]
    if not pending:
        return

    from tui_transcript.services.markdown_export import MarkdownExporter
    effective_output_dir = str(output_dir) if output_dir is not None else config.markdown_output_dir
    effective_course_name = course_name if course_name is not None else config.course_name
    exporter = MarkdownExporter(effective_output_dir)
    history = HistoryDB()
    output_mode = "markdown"
    next_seq = history.get_next_sequential_number(config.prefix)

    try:
        for idx, job in enumerate(pending):
            source_path = str(job.path)

            if history.is_already_processed(source_path, config.prefix, output_mode):
                record = history.get_processed_record(
                    source_path, config.prefix, output_mode
                )
                if record:
                    job.output_path = record.get("output_path", "") or ""
                cb.on_log(
                    f"Skipped: {job.path.name} "
                    f"(already processed with prefix '{config.prefix}')",
                    level=LogLevel.HIGHLIGHT,
                )
                job.status = JobStatus.DONE
                job.progress = 1.0
                cb.on_job_status_changed(job)
                cb.on_progress_advance(2)
                continue

            step_done = 0
            try:
                # --- Transcribe ---
                job.status = JobStatus.TRANSCRIBING
                job.progress = 0.3
                cb.on_job_status_changed(job)

                file_mb = job.path.stat().st_size / 1_048_576
                lang_label = LANGUAGES.get(job.language, job.language)
                cb.on_status_label(
                    f"Transcribing {job.path.name} ({file_mb:.0f} MB, {lang_label}) "
                    f"[{idx + 1}/{len(pending)}]..."
                )
                cb.on_log(
                    f"Transcribing: {job.path.name} "
                    f"({file_mb:.0f} MB, {lang_label})",
                    level=LogLevel.HIGHLIGHT,
                )

                def _on_status(msg: str) -> None:
                    cb.on_log(f"  {msg}", level=LogLevel.DIM)

                transcriber = get_transcriber(
                    job.engine,
                    model=job.whisper_model,
                    deepgram_api_key=config.deepgram_api_key,
                )
                transcript_result = await transcriber.transcribe(
                    job.path,
                    language=job.language,
                    on_status=_on_status,
                )
                job.transcript = transcript_result.text

                # --- Key Moments extraction (optional, requires ANTHROPIC_API_KEY) ---
                key_moments_dicts: list[dict] = []
                if config.anthropic_api_key and transcript_result.paragraphs:
                    cb.on_log("  Extracting key moments with Claude...", level=LogLevel.DIM)
                    job.key_moments = await extract_key_moments(
                        config.anthropic_api_key,
                        transcript_result.paragraphs,
                    )
                    key_moments_dicts = [
                        {"timestamp": m.timestamp, "description": m.description}
                        for m in job.key_moments
                    ]
                    cb.on_job_status_changed(job)

                cb.on_progress_advance(1)
                step_done = 1

                # --- Build title (with history-aware numbering) ---
                seq_number: int | None = None
                if config.naming_mode == NamingMode.SEQUENTIAL:
                    seq_number = next_seq
                    title = build_doc_title(config, job.path, next_seq)
                else:
                    title = build_doc_title(config, job.path, 0)
                    suffix = 2
                    base_title = title
                    while history.get_output_title_exists(title, output_mode):
                        title = f"{base_title}_{suffix}"
                        suffix += 1

                highlights_slug: str | None = None

                # --- Export ---
                job.status = JobStatus.UPLOADING
                job.progress = 0.8
                cb.on_job_status_changed(job)

                cb.on_status_label(
                    f"Saving {title}.md [{idx + 1}/{len(pending)}]..."
                )
                cb.on_log(f"Saving: {title}.md", level=LogLevel.HIGHLIGHT)
                date_str = datetime.fromtimestamp(
                    job.path.stat().st_mtime
                ).date().isoformat()
                duration_sec = get_media_duration_seconds(job.path)
                duration_min: int | None = None
                if duration_sec is not None:
                    duration_min = max(1, round(duration_sec / 60))
                if key_moments_dicts:
                    highlights_slug = str(uuid.uuid4())
                out_path = await asyncio.to_thread(
                    exporter.export,
                    title,
                    job.transcript,
                    date=date_str,
                    course_name=effective_course_name,
                    duration_minutes=duration_min,
                    key_moments=key_moments_dicts or None,
                    highlights_id=highlights_slug,
                )
                job.output_path = str(out_path)
                cb.on_log(f"Saved: {out_path}", level=LogLevel.SUCCESS)

                cb.on_progress_advance(1)
                step_done = 2
                job.status = JobStatus.DONE
                job.progress = 1.0
                cb.on_job_status_changed(job)

                history.record(
                    source_path=source_path,
                    prefix=config.prefix,
                    naming_mode=config.naming_mode.value,
                    sequential_number=seq_number,
                    output_title=title,
                    output_mode=output_mode,
                    output_path=job.output_path or None,
                    language=job.language,
                )

                doc_store = DocumentStore(db=history)
                doc_store.ensure_registered(effective_output_dir)
                if key_moments_dicts and highlights_slug and job.output_path:
                    history.save_highlights(
                        highlights_slug, job.output_path, key_moments_dicts
                    )
                    cb.on_log(
                        f"  Saved {len(key_moments_dicts)} key moments.",
                        level=LogLevel.DIM,
                    )

                # Index transcript for full-text search
                video_record = history.get_video_by_source_and_prefix(
                    source_path, config.prefix, output_mode
                )
                if video_record and job.transcript:
                    history.index_transcript(
                        video_record["id"],
                        title,
                        source_path,
                        job.transcript,
                    )

                if config.naming_mode == NamingMode.SEQUENTIAL:
                    next_seq += 1

            except Exception as exc:
                job.status = JobStatus.ERROR
                job.error = str(exc)
                # Keep progress at last value (0.3 or 0.8) to show where it failed
                cb.on_job_status_changed(job)
                cb.on_progress_advance(2 - step_done)

                tb = traceback.format_exc()
                cb.on_log(f"Error: {job.path.name} — {exc}", level=LogLevel.ERROR)
                cb.on_log(tb, level=LogLevel.DIM)
                logger.error("Job failed for %s:\n%s", job.path.name, tb)

        cb.on_status_label("Done!")
        cb.on_log("All tasks completed.", level=LogLevel.SUCCESS)
    finally:
        history.close()
