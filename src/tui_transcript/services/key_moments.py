"""Key moments extraction using Claude AI (claude-haiku-4-5)."""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tui_transcript.models import KeyMoment, TranscriptParagraph

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert at identifying the most important moments in a lecture or "
    "video transcript. Given timestamped paragraphs, extract the 5-10 most "
    "significant, insightful, or actionable segments. "
    "Return ONLY a JSON array (no markdown, no extra text) where each element "
    'has exactly two string fields: "timestamp" (H:MM:SS format from the input) '
    'and "description" (one concise sentence describing what happens at that moment).'
)


def _to_hms(seconds: float) -> str:
    t = int(seconds)
    return f"{t // 3600}:{(t % 3600) // 60:02d}:{t % 60:02d}"


async def extract_key_moments(
    api_key: str,
    paragraphs: list[TranscriptParagraph],
) -> list[KeyMoment]:
    """Extract key moments from transcript paragraphs via Claude.

    Returns an empty list on any failure — never crashes the pipeline.
    """
    from tui_transcript.models import KeyMoment

    if not api_key or not paragraphs:
        return []

    user_content = "\n\n".join(
        f"[{_to_hms(p.start)}] {p.text}" for p in paragraphs if p.text.strip()
    )
    if not user_content:
        return []

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key)
        msg = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = msg.content[0].text.strip()
        data = json.loads(raw)
        return [
            KeyMoment(
                timestamp=item["timestamp"],
                description=item["description"],
            )
            for item in data
            if isinstance(item, dict)
            and "timestamp" in item
            and "description" in item
        ]
    except Exception as exc:
        logger.warning("Key moments extraction failed: %s", exc)
        return []
