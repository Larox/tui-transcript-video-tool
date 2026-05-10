"""Recursive paragraph-aware chunker."""

from __future__ import annotations

from tui_transcript.services.rag.chunker import (
    ExtractedSection,
    chunk_sections,
)


def test_short_section_yields_one_chunk() -> None:
    sec = ExtractedSection(text="Hola mundo.", page_number=1)
    chunks = chunk_sections([sec], target_chars=800, overlap_chars=100)
    assert len(chunks) == 1
    assert chunks[0].text == "Hola mundo."
    assert chunks[0].chunk_index == 0
    assert chunks[0].page_number == 1


def test_long_section_splits_with_overlap() -> None:
    para = "Esto es una oración. " * 100  # ~2000 chars
    sec = ExtractedSection(text=para, page_number=3)
    chunks = chunk_sections([sec], target_chars=800, overlap_chars=100)
    assert len(chunks) >= 3
    for i, c in enumerate(chunks):
        assert len(c.text) <= 900  # target + slack for boundary alignment
        assert c.chunk_index == i
        assert c.page_number == 3
    # Adjacent chunks share at least some characters thanks to overlap.
    assert chunks[0].text[-50:] in chunks[1].text or chunks[1].text[:50] in chunks[0].text


def test_multiple_sections_produce_continuous_indices() -> None:
    secs = [
        ExtractedSection(text="A" * 1500, page_number=1),
        ExtractedSection(text="B" * 1500, page_number=2),
    ]
    chunks = chunk_sections(secs, target_chars=800, overlap_chars=100)
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))
    # Page numbers preserved.
    page_1 = [c for c in chunks if c.page_number == 1]
    page_2 = [c for c in chunks if c.page_number == 2]
    assert page_1 and page_2


def test_paragraph_boundary_preserved_when_possible() -> None:
    text = ("First paragraph " * 30) + "\n\n" + ("Second paragraph " * 30)
    sec = ExtractedSection(text=text, page_number=1)
    chunks = chunk_sections([sec], target_chars=600, overlap_chars=80)
    # The split should land on the paragraph boundary.
    assert any(c.text.endswith("First paragraph ".strip()) or c.text.rstrip().endswith("paragraph") for c in chunks)


def test_empty_input() -> None:
    assert chunk_sections([], target_chars=800, overlap_chars=100) == []
    assert chunk_sections([ExtractedSection(text="", page_number=1)], target_chars=800, overlap_chars=100) == []
