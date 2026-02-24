"""Shared transcription + export pipeline. Used by both TUI and web API."""

from __future__ import annotations

import asyncio
import logging
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from tui_transcript.models import (
    AppConfig,
    JobStatus,
    LANGUAGES,
    NamingMode,
    OutputMode,
    VideoJob,
    build_doc_title,
)
from tui_transcript.services.history import HistoryDB
from tui_transcript.services.transcription import transcribe

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


def _get_exporter(config: AppConfig):
    if config.output_mode == OutputMode.GOOGLE_DOCS:
        from tui_transcript.services.google_docs import GoogleDocsService
        return GoogleDocsService(config.google_service_account_json)
    from tui_transcript.services.markdown_export import MarkdownExporter
    return MarkdownExporter(config.markdown_output_dir)


async def run_pipeline(
    config: AppConfig,
    jobs: list[VideoJob],
    callbacks: PipelineCallbacks | None = None,
) -> None:
    """Run the transcription + export pipeline for pending jobs.

    Mutates jobs in place. Callbacks are invoked for progress, logs, and status.
    """
    cb = callbacks or DefaultPipelineCallbacks()
    pending = [j for j in jobs if j.status == JobStatus.PENDING]
    if not pending:
        return

    exporter = _get_exporter(config)
    history = HistoryDB()
    output_mode = config.output_mode.value
    next_seq = history.get_next_sequential_number(config.prefix)

    try:
        for idx, job in enumerate(pending):
            source_path = str(job.path)

            if history.is_already_processed(source_path, config.prefix, output_mode):
                cb.on_log(
                    f"Skipped: {job.path.name} "
                    f"(already processed with prefix '{config.prefix}')",
                    level=LogLevel.HIGHLIGHT,
                )
                job.status = JobStatus.DONE
                cb.on_job_status_changed(job)
                cb.on_progress_advance(2)
                continue

            step_done = 0
            try:
                # --- Transcribe ---
                job.status = JobStatus.TRANSCRIBING
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

                job.transcript = await transcribe(
                    config.deepgram_api_key,
                    job.path,
                    language=job.language,
                    on_status=_on_status,
                )
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

                # --- Export ---
                job.status = JobStatus.UPLOADING
                cb.on_job_status_changed(job)

                if config.output_mode == OutputMode.GOOGLE_DOCS:
                    cb.on_status_label(
                        f"Uploading {title} to Google Docs [{idx + 1}/{len(pending)}]..."
                    )
                    cb.on_log(f"Uploading: {title}", level=LogLevel.HIGHLIGHT)
                    doc_id = await asyncio.to_thread(
                        exporter.create_and_fill,
                        title,
                        config.drive_folder_id,
                        job.transcript,
                    )
                    job.doc_id = doc_id
                    job.doc_url = f"https://docs.google.com/document/d/{doc_id}"
                    cb.on_log(f"Created: {title} (ID: {doc_id})", level=LogLevel.SUCCESS)
                else:
                    cb.on_status_label(
                        f"Saving {title}.md [{idx + 1}/{len(pending)}]..."
                    )
                    cb.on_log(f"Saving: {title}.md", level=LogLevel.HIGHLIGHT)
                    out_path = await asyncio.to_thread(
                        exporter.export, title, job.transcript
                    )
                    job.output_path = str(out_path)
                    cb.on_log(f"Saved: {out_path}", level=LogLevel.SUCCESS)

                cb.on_progress_advance(1)
                step_done = 2
                job.status = JobStatus.DONE
                cb.on_job_status_changed(job)

                history.record(
                    source_path=source_path,
                    prefix=config.prefix,
                    naming_mode=config.naming_mode.value,
                    sequential_number=seq_number,
                    output_title=title,
                    output_mode=output_mode,
                    output_path=job.output_path or None,
                    doc_id=job.doc_id or None,
                    doc_url=job.doc_url or None,
                    language=job.language,
                )

                if config.naming_mode == NamingMode.SEQUENTIAL:
                    next_seq += 1

            except Exception as exc:
                job.status = JobStatus.ERROR
                job.error = str(exc)
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
