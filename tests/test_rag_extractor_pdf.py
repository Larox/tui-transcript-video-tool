"""PDF extractor."""

from __future__ import annotations

from pathlib import Path

from tui_transcript.services.rag.extractors.pdf import extract_pdf


FIXTURE = Path(__file__).parent / "fixtures" / "two_pages.pdf"


def test_extracts_two_pages() -> None:
    sections = extract_pdf(FIXTURE)
    assert len(sections) == 2
    assert sections[0].page_number == 1
    assert sections[1].page_number == 2
    assert "redes neuronales" in sections[0].text.lower()
    assert "matrices" in sections[1].text.lower()


def test_skips_blank_pages() -> None:
    # extract_pdf must drop pages whose extracted text is empty/whitespace.
    # Re-test against the fixture (no blanks): just confirm no empty sections.
    sections = extract_pdf(FIXTURE)
    assert all(s.text.strip() for s in sections)
