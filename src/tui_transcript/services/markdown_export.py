from __future__ import annotations

from pathlib import Path


class MarkdownExporter:
    def __init__(self, output_dir: str) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(self, title: str, transcript: str) -> Path:
        """Write a Markdown file and return its path."""
        safe_name = "".join(
            c if c.isalnum() or c in "-_ " else "_" for c in title
        )
        file_path = self.output_dir / f"{safe_name}.md"
        file_path.write_text(
            f"# {title}\n\n{transcript}\n", encoding="utf-8"
        )
        return file_path
