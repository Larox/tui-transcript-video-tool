"""Study materials generation using Claude AI (claude-haiku-4-5-20251001).

Generates 4 types of study materials from a class/lecture transcript:
  - Executive summary
  - Q&A pairs
  - Flashcards (concept/definition)
  - Action items (deadlines, homework, urgent notices)
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"

_SUMMARY_SYSTEM = (
    "You are an expert academic assistant. Given a class or lecture transcript, "
    "write a clear executive summary of 200-400 words covering the main topics, "
    "key takeaways, and overall purpose of the session. "
    "Return ONLY the plain summary text, no markdown headers, no extra commentary."
)

_QA_SYSTEM = (
    "You are an expert academic assistant. Given a class or lecture transcript, "
    "create exactly 10 question-answer pairs that cover the most important concepts. "
    "Return ONLY a JSON array (no markdown, no extra text) where each element "
    'has exactly two string fields: "question" and "answer".'
)

_FLASHCARD_SYSTEM = (
    "You are an expert academic assistant. Given a class or lecture transcript, "
    "create exactly 20 flashcard pairs for the key concepts introduced. "
    "Return ONLY a JSON array (no markdown, no extra text) where each element "
    'has exactly two string fields: "concept" and "definition".'
)

_ACTION_ITEMS_SYSTEM = (
    "You are an expert academic assistant. Given a class or lecture transcript, "
    "extract all action items: assignments, deadlines, homework, tasks, and urgent notices. "
    "For each item determine its urgency level (high/medium/low) and, if a date or deadline "
    "was explicitly mentioned, include it as a string in extracted_date (otherwise null). "
    "Return ONLY a JSON array (no markdown, no extra text) where each element has exactly "
    'three fields: "text" (string), "urgency" (one of "high", "medium", "low"), '
    'and "extracted_date" (string or null).'
)


async def generate_summary(transcript: str) -> str:
    """Generate a 200-400 word executive summary from a transcript.

    Returns an empty string on any failure — never crashes the pipeline.
    """
    if not transcript or not transcript.strip():
        return ""

    try:
        import os
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set; skipping summary generation")
            return ""

        client = anthropic.AsyncAnthropic(api_key=api_key)
        msg = await client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=_SUMMARY_SYSTEM,
            messages=[{"role": "user", "content": transcript}],
        )
        return msg.content[0].text.strip()
    except Exception as exc:
        logger.warning("Summary generation failed: %s", exc)
        return ""


async def generate_qa_pairs(transcript: str) -> list[dict]:
    """Generate 10 Q&A pairs from a transcript.

    Each dict has keys: ``question``, ``answer``.
    Returns an empty list on any failure — never crashes the pipeline.
    """
    if not transcript or not transcript.strip():
        return []

    try:
        import os
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set; skipping Q&A generation")
            return []

        client = anthropic.AsyncAnthropic(api_key=api_key)
        msg = await client.messages.create(
            model=_MODEL,
            max_tokens=2048,
            system=_QA_SYSTEM,
            messages=[{"role": "user", "content": transcript}],
        )
        raw = msg.content[0].text.strip()
        data = json.loads(raw)
        return [
            {"question": item["question"], "answer": item["answer"]}
            for item in data
            if isinstance(item, dict) and "question" in item and "answer" in item
        ]
    except Exception as exc:
        logger.warning("Q&A generation failed: %s", exc)
        return []


async def generate_flashcards(transcript: str) -> list[dict]:
    """Generate 20 flashcard concept/definition pairs from a transcript.

    Each dict has keys: ``concept``, ``definition``.
    Returns an empty list on any failure — never crashes the pipeline.
    """
    if not transcript or not transcript.strip():
        return []

    try:
        import os
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set; skipping flashcard generation")
            return []

        client = anthropic.AsyncAnthropic(api_key=api_key)
        msg = await client.messages.create(
            model=_MODEL,
            max_tokens=2048,
            system=_FLASHCARD_SYSTEM,
            messages=[{"role": "user", "content": transcript}],
        )
        raw = msg.content[0].text.strip()
        data = json.loads(raw)
        return [
            {"concept": item["concept"], "definition": item["definition"]}
            for item in data
            if isinstance(item, dict) and "concept" in item and "definition" in item
        ]
    except Exception as exc:
        logger.warning("Flashcard generation failed: %s", exc)
        return []


async def generate_action_items(transcript: str) -> list[dict]:
    """Extract action items (deadlines, homework, urgent notices) from a transcript.

    Each dict has keys: ``text``, ``urgency`` (high/medium/low), ``extracted_date`` (str or None).
    Returns an empty list on any failure — never crashes the pipeline.
    """
    if not transcript or not transcript.strip():
        return []

    try:
        import os
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set; skipping action items generation")
            return []

        client = anthropic.AsyncAnthropic(api_key=api_key)
        msg = await client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=_ACTION_ITEMS_SYSTEM,
            messages=[{"role": "user", "content": transcript}],
        )
        raw = msg.content[0].text.strip()
        data = json.loads(raw)
        return [
            {
                "text": item["text"],
                "urgency": item.get("urgency", "medium"),
                "extracted_date": item.get("extracted_date"),
            }
            for item in data
            if isinstance(item, dict) and "text" in item
        ]
    except Exception as exc:
        logger.warning("Action items generation failed: %s", exc)
        return []


async def generate_all(transcript: str) -> dict:
    """Run all 4 generators and return a combined result dict.

    Keys: ``summary``, ``qa_pairs``, ``flashcards``, ``action_items``.
    Each sub-result follows the same empty-on-failure contract as the
    individual functions.
    """
    summary, qa_pairs, flashcards, action_items = (
        await generate_summary(transcript),
        await generate_qa_pairs(transcript),
        await generate_flashcards(transcript),
        await generate_action_items(transcript),
    )
    return {
        "summary": summary,
        "qa_pairs": qa_pairs,
        "flashcards": flashcards,
        "action_items": action_items,
    }
