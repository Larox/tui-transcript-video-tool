from __future__ import annotations

import logging
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
    NamingMode,
    OutputMode,
    VideoJob,
)
from tui_transcript.screens.config import ConfigScreen
from tui_transcript.screens.file_picker import FilePickerScreen
from tui_transcript.services.pipeline import (
    LogLevel,
    run_pipeline,
)

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

    def _log_with_level(self, msg: str, level: str = LogLevel.INFO) -> None:
        """Write to TUI log with Rich markup based on level."""
        markup = {
            LogLevel.HIGHLIGHT: f"[bold cyan]{msg}[/]",
            LogLevel.SUCCESS: f"[bold green]{msg}[/]",
            LogLevel.WARNING: f"[bold yellow]{msg}[/]",
            LogLevel.ERROR: f"[bold red]{msg}[/]",
            LogLevel.DIM: f"[dim]{msg}[/]",
        }.get(level, msg)
        self._log(markup)

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

        class TUIPipelineCallbacks:
            def on_log(_, msg: str, level: str = LogLevel.INFO) -> None:
                self._log_with_level(msg, level)

            def on_job_status_changed(_, job: VideoJob) -> None:
                self._refresh_jobs()

            def on_progress_advance(_, steps: int = 1) -> None:
                for _ in range(steps):
                    progress.advance(1)

            def on_status_label(_, label: str) -> None:
                status_label.update(label)

        await run_pipeline(
            self.config,
            self.jobs,
            callbacks=TUIPipelineCallbacks(),
        )

        btn.disabled = False
        self._processing = False
