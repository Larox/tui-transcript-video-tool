from __future__ import annotations

import asyncio
import logging
import traceback
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ProgressBar,
    RichLog,
    Select,
    Static,
)

from tui_transcript.models import (
    AppConfig,
    JobStatus,
    LANGUAGES,
    OutputMode,
    VideoJob,
    build_doc_title,
)
from tui_transcript.screens.config import ConfigScreen
from tui_transcript.screens.file_picker import FilePickerScreen
from tui_transcript.services.transcription import transcribe

logger = logging.getLogger(__name__)

LANGUAGE_OPTIONS = [(f"{name} ({code})", code) for code, name in LANGUAGES.items()]


class JobRow(Horizontal):
    """A dashboard row for a single VideoJob with language select and remove."""

    DEFAULT_CSS = """
    JobRow {
        height: 3;
        padding: 0 1;
    }
    JobRow .job-name {
        width: 1fr;
        content-align-vertical: middle;
    }
    JobRow Select {
        width: 22;
        margin: 0 1;
    }
    JobRow .job-status {
        width: 16;
        content-align-vertical: middle;
    }
    JobRow .btn-remove-job {
        width: 6;
        min-width: 6;
    }
    """

    def __init__(self, job: VideoJob, **kwargs) -> None:
        super().__init__(**kwargs)
        self.job = job

    def compose(self) -> ComposeResult:
        yield Static(self.job.path.name, classes="job-name")
        yield Select(
            LANGUAGE_OPTIONS,
            value=self.job.language,
            allow_blank=False,
        )
        yield Label(self.job.status.value, classes="job-status")
        yield Button("X", variant="error", classes="btn-remove-job")

    def refresh_status(self) -> None:
        self.query_one(".job-status", Label).update(self.job.status.value)
        locked = self.job.status != JobStatus.PENDING
        self.query_one(Select).disabled = locked
        self.query_one(".btn-remove-job", Button).disabled = locked


def _job_widget_id(job: VideoJob) -> str:
    return f"job-{hash(str(job.path)) & 0xFFFFFFFF}"


class DashboardScreen(Screen):
    BINDINGS = [("ctrl+q", "quit", "Quit")]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.jobs: list[VideoJob] = []
        self._processing = False

    @property
    def config(self) -> AppConfig:
        return self.app.config  # type: ignore[attr-defined]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Vertical(id="dashboard"):
            mode = "Google Docs" if self.app.config.output_mode == OutputMode.GOOGLE_DOCS else "Local Markdown"  # type: ignore[attr-defined]
            yield Label(f"Output mode: {mode}", id="mode_banner")

            with Horizontal(id="file-input-row"):
                yield Button("Browse", variant="primary", id="btn_browse")
                yield Button("Settings", variant="default", id="btn_settings")

            yield VerticalScroll(id="job_list")
            yield Label("Overall Progress", classes="section-label")
            yield ProgressBar(id="overall_progress", total=100, show_eta=False)
            yield Label("", id="status_label")

            with Horizontal(id="action-row"):
                yield Button(
                    "Start", variant="success", id="btn_start"
                )
                yield Button(
                    "Clear", variant="warning", id="btn_clear"
                )

            yield Label("Logs", classes="section-label")
            yield RichLog(id="log", highlight=True, markup=True)

        yield Footer()

    def _log(self, msg: str) -> None:
        """Write to both the TUI log panel and the file log."""
        self.query_one("#log", RichLog).write(msg)
        logger.info(msg)

    # --- File management ---

    @on(Button.Pressed, "#btn_browse")
    def _open_file_picker(self) -> None:
        self.app.push_screen(
            FilePickerScreen(start_path=str(Path.home())),
            callback=self._on_files_picked,
        )

    @on(Button.Pressed, "#btn_settings")
    def _open_settings(self) -> None:
        self.app.push_screen(
            ConfigScreen(is_revisit=True),
            callback=self._on_settings_closed,
        )

    def _on_settings_closed(self, _result: object = None) -> None:
        mode = "Google Docs" if self.config.output_mode == OutputMode.GOOGLE_DOCS else "Local Markdown"
        self.query_one("#mode_banner", Label).update(f"Output mode: {mode}")

    def _on_files_picked(self, selections: list[tuple[Path, str]]) -> None:
        if not selections:
            return
        container = self.query_one("#job_list", VerticalScroll)
        added = 0
        for path, language in selections:
            if any(j.path == path for j in self.jobs):
                continue
            job = VideoJob(path=path, language=language)
            self.jobs.append(job)
            container.mount(JobRow(job, id=_job_widget_id(job)))
            added += 1
        if added:
            self.notify(f"Added {added} file(s)", severity="information")

    def _refresh_jobs(self) -> None:
        """Update status text and disabled state on all existing JobRow widgets."""
        for job in self.jobs:
            wid = _job_widget_id(job)
            try:
                row = self.query_one(f"#{wid}", JobRow)
                row.refresh_status()
            except Exception:
                pass

    @on(Select.Changed)
    def _lang_changed(self, event: Select.Changed) -> None:
        for widget in event.select.ancestors_with_self:
            if isinstance(widget, JobRow):
                widget.job.language = str(event.value)
                break

    @on(Button.Pressed, ".btn-remove-job")
    def _remove_job(self, event: Button.Pressed) -> None:
        if self._processing:
            self.notify("Cannot remove while processing", severity="warning")
            return
        for widget in event.button.ancestors_with_self:
            if isinstance(widget, JobRow):
                if widget.job in self.jobs:
                    self.jobs.remove(widget.job)
                widget.remove()
                break

    @on(Button.Pressed, "#btn_clear")
    def _clear_files(self) -> None:
        if self._processing:
            self.notify("Cannot clear while processing", severity="warning")
            return
        self.jobs.clear()
        self.query_one("#job_list", VerticalScroll).remove_children()
        self.query_one("#overall_progress", ProgressBar).update(progress=0)
        self.query_one("#status_label", Label).update("")
        self.query_one("#log", RichLog).clear()

    # --- Processing pipeline ---

    @on(Button.Pressed, "#btn_start")
    def _start_processing(self) -> None:
        if self._processing:
            self.notify("Already processing", severity="warning")
            return
        pending = [j for j in self.jobs if j.status == JobStatus.PENDING]
        if not pending:
            self.notify("No pending files to process", severity="warning")
            return
        self._run_pipeline()

    @work(exclusive=True)
    async def _run_pipeline(self) -> None:
        self._processing = True
        btn = self.query_one("#btn_start", Button)
        btn.disabled = True
        progress = self.query_one("#overall_progress", ProgressBar)
        status_label = self.query_one("#status_label", Label)

        pending = [j for j in self.jobs if j.status == JobStatus.PENDING]
        total = len(pending)
        progress.update(total=total * 2, progress=0)

        self._refresh_jobs()

        exporter = self._get_exporter()

        for idx, job in enumerate(pending):
            overall_idx = self.jobs.index(job)
            step_done = 0
            try:
                # --- Transcribe ---
                job.status = JobStatus.TRANSCRIBING
                self._refresh_jobs()

                file_mb = job.path.stat().st_size / 1_048_576
                lang_label = LANGUAGES.get(job.language, job.language)
                status_label.update(
                    f"Transcribing {job.path.name} ({file_mb:.0f} MB, {lang_label}) "
                    f"[{idx + 1}/{total}]..."
                )
                self._log(
                    f"[bold cyan]Transcribing:[/] {job.path.name} "
                    f"({file_mb:.0f} MB, {lang_label})"
                )

                def _on_status(msg: str) -> None:
                    self._log(f"  [dim]{msg}[/]")

                job.transcript = await transcribe(
                    self.config.deepgram_api_key,
                    job.path,
                    language=job.language,
                    on_status=_on_status,
                )
                progress.advance(1)
                step_done = 1

                # --- Export ---
                job.status = JobStatus.UPLOADING
                self._refresh_jobs()
                title = build_doc_title(self.config, job.path, overall_idx)

                if self.config.output_mode == OutputMode.GOOGLE_DOCS:
                    status_label.update(
                        f"Uploading {title} to Google Docs [{idx + 1}/{total}]..."
                    )
                    self._log(f"[bold yellow]Uploading:[/] {title}")
                    doc_id = await asyncio.to_thread(
                        exporter.create_and_fill,
                        title,
                        self.config.drive_folder_id,
                        job.transcript,
                    )
                    job.doc_id = doc_id
                    job.doc_url = f"https://docs.google.com/document/d/{doc_id}"
                    self._log(
                        f"[bold green]Created:[/] {title} "
                        f"(ID: {doc_id})"
                    )
                else:
                    status_label.update(
                        f"Saving {title}.md [{idx + 1}/{total}]..."
                    )
                    self._log(f"[bold yellow]Saving:[/] {title}.md")
                    out_path = await asyncio.to_thread(
                        exporter.export, title, job.transcript
                    )
                    job.output_path = str(out_path)
                    self._log(
                        f"[bold green]Saved:[/] {out_path}"
                    )

                progress.advance(1)
                step_done = 2
                job.status = JobStatus.DONE
                self._refresh_jobs()

            except Exception as exc:
                job.status = JobStatus.ERROR
                job.error = str(exc)
                self._refresh_jobs()
                progress.advance(2 - step_done)

                tb = traceback.format_exc()
                self._log(
                    f"[bold red]Error:[/] {job.path.name} — {exc}"
                )
                self._log(f"[dim red]{tb}[/]")
                logger.error("Job failed for %s:\n%s", job.path.name, tb)

        status_label.update("Done!")
        self._log("[bold green]All tasks completed.[/]")
        btn.disabled = False
        self._processing = False

    def _get_exporter(self):
        if self.config.output_mode == OutputMode.GOOGLE_DOCS:
            from tui_transcript.services.google_docs import GoogleDocsService
            return GoogleDocsService(self.config.google_service_account_json)
        else:
            from tui_transcript.services.markdown_export import MarkdownExporter
            return MarkdownExporter(self.config.markdown_output_dir)
