"""Extractor registry — maps mime types to extraction functions.

Adding a new format (e.g. .ipynb) is one new module + one entry in this dict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from tui_transcript.services.rag.chunker import ExtractedSection
from tui_transcript.services.rag.extractors.pdf import extract_pdf

Extractor = Callable[[Path], list[ExtractedSection]]

REGISTRY: dict[str, Extractor] = {
    "application/pdf": extract_pdf,
}


def get_extractor(mime_type: str) -> Extractor | None:
    return REGISTRY.get(mime_type)
