"""Transcript extractor reads from history.transcript_search."""

from __future__ import annotations

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.extractors.transcript import extract_transcript


def test_extracts_paragraphs(db: HistoryDB) -> None:
    # Seed a video + transcript.
    db.record(
        source_path="/v/lec.mp4",
        prefix="Test",
        naming_mode="sequential",
        sequential_number=1,
        output_title="Lec",
        output_mode="markdown",
        output_path="/o/Lec.md",
        language="es",
    )
    vid = db._conn.execute("SELECT id FROM processed_videos").fetchone()[0]
    db.index_transcript(vid, "Lec", "/v/lec.mp4", "Primer parrafo.\n\nSegundo parrafo.\n\nTercero.")
    sections = extract_transcript(vid, db=db)
    assert len(sections) == 3
    assert sections[0].text == "Primer parrafo."
    assert sections[1].text == "Segundo parrafo."
    assert sections[2].text == "Tercero."
    assert all(s.page_number is None for s in sections)


def test_returns_empty_when_no_transcript(db: HistoryDB) -> None:
    assert extract_transcript(999, db=db) == []
