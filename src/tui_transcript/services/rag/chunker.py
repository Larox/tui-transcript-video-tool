"""Paragraph-aware recursive chunker.

Splits each ExtractedSection into chunks of approximately `target_chars`,
preferring paragraph boundaries (`\n\n`), then sentence boundaries (`. `),
then character boundaries. Adjacent chunks overlap by `overlap_chars`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExtractedSection:
    """One unit of upstream content (e.g. one PDF page, one transcript paragraph)."""

    text: str
    page_number: int | None = None


@dataclass
class ChunkOut:
    """One produced chunk, before embedding."""

    text: str
    chunk_index: int
    page_number: int | None


def chunk_sections(
    sections: list[ExtractedSection],
    *,
    target_chars: int = 800,
    overlap_chars: int = 100,
) -> list[ChunkOut]:
    """Chunk a list of sections, preserving page provenance."""
    out: list[ChunkOut] = []
    idx = 0
    for sec in sections:
        text = (sec.text or "").strip()
        if not text:
            continue
        for piece in _split_one(text, target_chars=target_chars, overlap_chars=overlap_chars):
            out.append(ChunkOut(text=piece, chunk_index=idx, page_number=sec.page_number))
            idx += 1
    return out


def _split_one(text: str, *, target_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= target_chars:
        return [text]
    pieces: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + target_chars, n)
        if end < n:
            # Prefer paragraph break in the second half of the window.
            window_start = start + target_chars // 2
            cut = text.rfind("\n\n", window_start, end)
            if cut == -1:
                cut = text.rfind(". ", window_start, end)
                if cut != -1:
                    cut += 2  # include the ". "
            if cut != -1 and cut > start:
                end = cut
        pieces.append(text[start:end].strip())
        if end >= n:
            break
        start = max(end - overlap_chars, start + 1)
    return [p for p in pieces if p]
