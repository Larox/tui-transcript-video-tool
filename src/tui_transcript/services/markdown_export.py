from __future__ import annotations

from pathlib import Path


def _build_front_matter(
    date: str,
    lecture_title: str,
    course_name: str,
    duration_minutes: int | None,
    highlights_id: str | None = None,
) -> str:
    """Build YAML front matter block for LLM-ready markdown."""
    lines = [
        "---",
        f"date: {date}",
        f"lecture_title: {lecture_title}",
        f"course_name: {course_name}",
    ]
    if duration_minutes is not None:
        lines.append(f"video_duration_minutes: {duration_minutes}")
    if highlights_id is not None:
        lines.append(f"highlights_id: {highlights_id}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


class MarkdownExporter:
    def __init__(self, output_dir: str) -> None:
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        title: str,
        transcript: str,
        *,
        date: str,
        course_name: str,
        duration_minutes: int | None = None,
        key_moments: list[dict] | None = None,
        highlights_id: str | None = None,
    ) -> Path:
        """Write a Markdown file with YAML front matter and return its path."""
        safe_name = "".join(
            c if c.isalnum() or c in "-_ " else "_" for c in title
        )
        file_path = self.output_dir / f"{safe_name}.md"
        front_matter = _build_front_matter(
            date=date,
            lecture_title=title,
            course_name=course_name,
            duration_minutes=duration_minutes,
            highlights_id=highlights_id,
        )
        moments_section = ""
        if key_moments:
            lines = ["## Key Moments", ""]
            for m in key_moments:
                lines.append(f"- **{m['timestamp']}** — {m['description']}")
            moments_section = "\n".join(lines) + "\n\n"
        content = f"{front_matter}# {title}\n\n{moments_section}{transcript}\n"
        file_path.write_text(content, encoding="utf-8")
        return file_path
