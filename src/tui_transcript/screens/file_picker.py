from __future__ import annotations

from pathlib import Path
from typing import Iterable

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.suggester import Suggester
from textual.widgets import (
    Button,
    DirectoryTree,
    Input,
    Label,
    Select,
    Static,
)

from tui_transcript.models import LANGUAGES

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv",
    ".m4a", ".mp3", ".wav", ".ogg", ".flac",
}

LANGUAGE_OPTIONS = [(f"{name} ({code})", code) for code, name in LANGUAGES.items()]


class PathSuggester(Suggester):
    """Suggests filesystem directory paths as the user types."""

    async def get_suggestion(self, value: str) -> str | None:
        if not value:
            return None
        p = Path(value).expanduser()
        if p.is_dir() and value.endswith("/"):
            children = sorted(
                (c for c in p.iterdir() if c.is_dir()),
                key=lambda c: c.name.lower(),
            )
            if children:
                return str(children[0]) + "/"
            return None
        parent = p.parent
        prefix = p.name
        if not parent.is_dir():
            return None
        matches = sorted(
            (c for c in parent.iterdir() if c.is_dir() and c.name.startswith(prefix)),
            key=lambda c: c.name.lower(),
        )
        if matches:
            return str(matches[0]) + "/"
        return None


class VideoDirectoryTree(DirectoryTree):
    """DirectoryTree that only shows directories and video/audio files."""

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [
            p for p in paths
            if p.is_dir() or p.suffix.lower() in VIDEO_EXTENSIONS
        ]


class FileEntry(Horizontal):
    """A row representing a selected file with language picker and remove button."""

    DEFAULT_CSS = """
    FileEntry {
        height: 3;
        padding: 0 1;
    }
    FileEntry .file-name {
        width: 1fr;
        content-align-vertical: middle;
    }
    FileEntry Select {
        width: 22;
        margin: 0 1;
    }
    FileEntry .btn-remove {
        width: 6;
        min-width: 6;
    }
    """

    def __init__(self, file_path: Path, language: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.file_path = file_path
        self.language = language

    def compose(self) -> ComposeResult:
        size_mb = self.file_path.stat().st_size / 1_048_576
        yield Static(
            f"{self.file_path.name}  ({size_mb:.0f} MB)",
            classes="file-name",
        )
        yield Select(
            LANGUAGE_OPTIONS,
            value=self.language,
            allow_blank=False,
        )
        yield Button("X", variant="error", classes="btn-remove")


class FilePickerScreen(ModalScreen[list[tuple[Path, str]]]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, start_path: str = ".", **kwargs) -> None:
        super().__init__(**kwargs)
        self._start_path = start_path
        self._default_lang = "es"
        self.selected: dict[Path, str] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="picker"):
            yield Label("File Picker", id="picker-title")
            with Horizontal(id="picker-nav"):
                yield Input(
                    value=self._start_path,
                    placeholder="Root directory — press Enter to navigate",
                    id="root_input",
                    suggester=PathSuggester(case_sensitive=True),
                )
            yield VideoDirectoryTree(self._start_path, id="dir_tree")
            yield Label("Selected (0)", id="selected_count")
            yield VerticalScroll(id="selected_list")
            with Horizontal(id="picker-actions"):
                yield Button("Add Selected", variant="success", id="btn_pick")
                yield Button("Cancel", variant="error", id="btn_cancel")

    @on(Input.Submitted, "#root_input")
    def _change_root(self) -> None:
        raw = self.query_one("#root_input", Input).value.strip()
        root = Path(raw).expanduser().resolve()
        if not root.is_dir():
            self.notify(f"Not a directory: {raw}", severity="error")
            return
        tree = self.query_one("#dir_tree", VideoDirectoryTree)
        tree.path = root
        tree.reload()

    @staticmethod
    def _entry_id(path: Path) -> str:
        return f"entry-{hash(str(path)) & 0xFFFFFFFF}"

    @on(DirectoryTree.FileSelected)
    def _file_clicked(self, event: DirectoryTree.FileSelected) -> None:
        path = event.path.resolve()
        container = self.query_one("#selected_list", VerticalScroll)
        entry_id = self._entry_id(path)

        if path in self.selected:
            self.selected.pop(path)
            try:
                container.query_one(f"#{entry_id}", FileEntry).remove()
            except Exception:
                pass
        else:
            self.selected[path] = self._default_lang
            container.mount(FileEntry(path, self._default_lang, id=entry_id))

        self._update_count()

    def _update_count(self) -> None:
        self.query_one("#selected_count", Label).update(
            f"Selected ({len(self.selected)})"
        )

    @on(Select.Changed)
    def _lang_changed(self, event: Select.Changed) -> None:
        for widget in event.select.ancestors_with_self:
            if isinstance(widget, FileEntry):
                widget.language = str(event.value)
                self.selected[widget.file_path] = str(event.value)
                break

    @on(Button.Pressed, ".btn-remove")
    def _remove_entry(self, event: Button.Pressed) -> None:
        for widget in event.button.ancestors_with_self:
            if isinstance(widget, FileEntry):
                self.selected.pop(widget.file_path, None)
                widget.remove()
                self._update_count()
                break

    @on(Button.Pressed, "#btn_pick")
    def _pick(self) -> None:
        result = [(path, lang) for path, lang in self.selected.items()]
        self.dismiss(result)

    @on(Button.Pressed, "#btn_cancel")
    def _cancel(self) -> None:
        self.dismiss([])

    def action_cancel(self) -> None:
        self.dismiss([])


class _DirOnlyTree(DirectoryTree):
    """DirectoryTree that only shows directories."""

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [p for p in paths if p.is_dir()]


class DirPickerScreen(ModalScreen[str]):
    """Modal for selecting a single directory."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, start_path: str = ".", **kwargs) -> None:
        super().__init__(**kwargs)
        self._start_path = str(Path(start_path).expanduser().resolve())
        self._selected: str = self._start_path

    def compose(self) -> ComposeResult:
        with Vertical(id="dir-picker"):
            yield Label("Select Directory", id="dir-picker-title")
            with Horizontal(id="dir-picker-nav"):
                yield Input(
                    value=self._start_path,
                    placeholder="Directory path — press Enter to navigate",
                    id="dir_input",
                    suggester=PathSuggester(case_sensitive=True),
                )
            yield _DirOnlyTree(self._start_path, id="dir_only_tree")
            yield Label(f"Selected: {self._selected}", id="dir_selected_label")
            with Horizontal(id="dir-picker-actions"):
                yield Button("Select", variant="success", id="btn_dir_select")
                yield Button("Cancel", variant="error", id="btn_dir_cancel")

    @on(Input.Submitted, "#dir_input")
    def _change_root(self) -> None:
        raw = self.query_one("#dir_input", Input).value.strip()
        root = Path(raw).expanduser().resolve()
        if not root.is_dir():
            self.notify(f"Not a directory: {raw}", severity="error")
            return
        tree = self.query_one("#dir_only_tree", _DirOnlyTree)
        tree.path = root
        tree.reload()
        self._selected = str(root)
        self.query_one("#dir_selected_label", Label).update(
            f"Selected: {self._selected}"
        )

    @on(DirectoryTree.DirectorySelected)
    def _dir_clicked(self, event: DirectoryTree.DirectorySelected) -> None:
        self._selected = str(event.path.resolve())
        self.query_one("#dir_selected_label", Label).update(
            f"Selected: {self._selected}"
        )

    @on(Button.Pressed, "#btn_dir_select")
    def _select(self) -> None:
        self.dismiss(self._selected)

    @on(Button.Pressed, "#btn_dir_cancel")
    def _cancel(self) -> None:
        self.dismiss("")

    def action_cancel(self) -> None:
        self.dismiss("")
