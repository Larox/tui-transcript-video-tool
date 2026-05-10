"""PDF text extraction via pypdf."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from tui_transcript.services.rag.chunker import ExtractedSection


def extract_pdf(path: Path) -> list[ExtractedSection]:
    reader = PdfReader(str(path))
    out: list[ExtractedSection] = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        out.append(ExtractedSection(text=text, page_number=i))
    return out
