from __future__ import annotations

import logging

from textual.app import App

from tui_transcript.models import AppConfig
from tui_transcript.screens.config import ConfigScreen
from tui_transcript.screens.dashboard import DashboardScreen

LOG_FILE = "tui_transcript.log"


class TranscriptApp(App):
    """TUI Video-to-Docs: transcribe videos and export to Google Docs or Markdown."""

    TITLE = "TUI Video-to-Docs"
    CSS_PATH = "styles.tcss"
    SCREENS = {"config": ConfigScreen, "dashboard": DashboardScreen}
    BINDINGS = [("ctrl+q", "quit", "Quit")]

    config: AppConfig = AppConfig()

    def on_mount(self) -> None:
        self.push_screen("config")


def main() -> None:
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        filemode="w",
    )
    logging.getLogger().info("TUI Video-to-Docs starting")

    app = TranscriptApp()
    app.run()


if __name__ == "__main__":
    main()
