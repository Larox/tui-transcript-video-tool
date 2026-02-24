from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    RadioButton,
    RadioSet,
    Static,
)

from tui_transcript.models import AppConfig, NamingMode
from tui_transcript.screens.file_picker import DirPickerScreen
from tui_transcript.services.config_store import EnvConfigStore


class ConfigScreen(Screen):
    BINDINGS = [("ctrl+q", "quit", "Quit")]

    def __init__(self, is_revisit: bool = False, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._is_revisit = is_revisit
        self._md_output_dir = ""

    def compose(self) -> ComposeResult:
        config_store = EnvConfigStore()
        config = config_store.load()

        yield Header(show_clock=True)
        with VerticalScroll(id="config-scroll"):
            yield Label("Deepgram API Key *", classes="field-label")
            yield Input(
                value=config.deepgram_api_key,
                placeholder="dg-...",
                password=True,
                id="deepgram_key",
            )

            yield Static(" ")
            yield Label(
                "Google Service Account JSON (optional)",
                classes="field-label",
            )
            yield Input(
                value=config.google_service_account_json,
                placeholder="/path/to/service-account.json",
                id="google_json",
            )

            yield Label(
                "Google Drive Folder ID (optional)", classes="field-label"
            )
            yield Input(
                value=config.drive_folder_id,
                placeholder="1aBcDeFgHiJkLmNoPqRsTuVwXyZ",
                id="drive_folder",
            )

            yield Static(" ")
            yield Label(
                "Markdown Output Directory", classes="field-label"
            )
            self._md_output_dir = config.markdown_output_dir
            with Horizontal(id="md-output-row"):
                yield Label(self._md_output_dir, id="md_output_dir_label")
                yield Button("Browse", variant="primary", id="btn_md_browse")

            yield Static(" ")
            yield Label("Naming Mode", classes="field-label")
            saved_mode = config.naming_mode.value
            with RadioSet(id="naming_mode"):
                yield RadioButton(
                    "Sequential  (Prefix_1, Prefix_2, ...)",
                    value=saved_mode == "sequential",
                    id="mode_seq",
                )
                yield RadioButton(
                    "Original  (Prefix_FileName)",
                    value=saved_mode == "original",
                    id="mode_orig",
                )

            yield Label("Prefix", classes="field-label")
            yield Input(
                value=config.prefix,
                placeholder="Transcripcion",
                id="prefix",
            )

            yield Static(" ")
            yield Label("", id="output_mode_label")

            with Center():
                yield Button("Continue", variant="primary", id="btn_continue")

        yield Footer()

    def on_mount(self) -> None:
        self._update_output_label()

    @on(Input.Changed, "#google_json")
    @on(Input.Changed, "#drive_folder")
    def _google_fields_changed(self) -> None:
        self._update_output_label()

    def _update_output_label(self) -> None:
        gj = self.query_one("#google_json", Input).value.strip()
        df = self.query_one("#drive_folder", Input).value.strip()
        label = self.query_one("#output_mode_label", Label)
        if gj and df:
            label.update("Output: Google Docs")
        else:
            label.update("Output: Local Markdown (.md)")

    @on(Button.Pressed, "#btn_md_browse")
    def _open_dir_picker(self) -> None:
        self.app.push_screen(
            DirPickerScreen(start_path=self._md_output_dir),
            callback=self._on_dir_picked,
        )

    def _on_dir_picked(self, result: str) -> None:
        if result:
            self._md_output_dir = result
            self.query_one("#md_output_dir_label", Label).update(result)

    @on(Button.Pressed, "#btn_continue")
    def _continue(self) -> None:
        dg_key = self.query_one("#deepgram_key", Input).value.strip()
        if not dg_key:
            self.notify("Deepgram API Key is required", severity="error")
            return

        gj = self.query_one("#google_json", Input).value.strip()
        if gj and not Path(gj).is_file():
            self.notify(
                "Google JSON path does not exist", severity="error"
            )
            return

        df = self.query_one("#drive_folder", Input).value.strip()
        md_dir = self._md_output_dir.strip() or "./output"
        prefix = self.query_one("#prefix", Input).value.strip() or "Transcripcion"

        radio_set = self.query_one("#naming_mode", RadioSet)
        naming = NamingMode.SEQUENTIAL
        if radio_set.pressed_index == 1:
            naming = NamingMode.ORIGINAL

        config = AppConfig(
            deepgram_api_key=dg_key,
            google_service_account_json=gj,
            drive_folder_id=df,
            naming_mode=naming,
            prefix=prefix,
            markdown_output_dir=md_dir,
        )

        EnvConfigStore().save(config)
        self.app.config = config  # type: ignore[attr-defined]
        if self._is_revisit:
            self.app.pop_screen()
        else:
            self.app.push_screen("dashboard")
