"""Pull a video's transcript text from history.transcript_search and split into paragraphs.

Transcripts arrive without page boundaries; we split on blank lines (the
standard paragraph separator emitted by both Deepgram and Whisper exports).
"""

from __future__ import annotations

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.chunker import ExtractedSection


def extract_transcript(video_id: int, *, db: HistoryDB | None = None) -> list[ExtractedSection]:
    own = db is None
    if own:
        db = HistoryDB()
    try:
        text = db.get_transcript_content(video_id)
        if not text:
            return []
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return [ExtractedSection(text=p, page_number=None) for p in paragraphs]
    finally:
        if own:
            db.close()
