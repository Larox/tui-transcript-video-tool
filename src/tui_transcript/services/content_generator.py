"""Study materials generation using PydanticAI (provider-agnostic).

Provider is controlled via env vars:
  AI_PROVIDER  — 'anthropic' (default) | 'openai' | 'google'
  AI_MODEL     — model name override (e.g. 'gpt-4o', 'gemini-2.0-flash')

API keys are read from the standard env vars for each provider:
  ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY / GEMINI_API_KEY
"""
from __future__ import annotations

import logging
import os
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------

def _get_model() -> str:
    """Return a PydanticAI model string based on env config. Read at call time."""
    provider = os.environ.get("AI_PROVIDER", "anthropic").lower()
    model_name = os.environ.get("AI_MODEL", "")
    if provider == "openai":
        return f"openai:{model_name or 'gpt-4o'}"
    if provider == "google":
        return f"google-gla:{model_name or 'gemini-2.0-flash'}"
    return f"anthropic:{model_name or 'claude-sonnet-4-6'}"


def _has_api_key() -> bool:
    provider = os.environ.get("AI_PROVIDER", "anthropic").lower()
    if provider == "openai":
        return bool(os.environ.get("OPENAI_API_KEY"))
    if provider == "google":
        return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


# ---------------------------------------------------------------------------
# Internal Pydantic models (schema enforced by PydanticAI tool use)
# ---------------------------------------------------------------------------

class _QAItem(BaseModel):
    question: str
    answer: str
    starred: bool = False

class _QAResult(BaseModel):
    pairs: list[_QAItem]

class _FlashcardItem(BaseModel):
    concept: str
    definition: str
    starred: bool = False

class _FlashcardResult(BaseModel):
    cards: list[_FlashcardItem]

class _ActionItem(BaseModel):
    text: str
    urgency: Literal["high", "medium", "low"] = "medium"
    extracted_date: str | None = None

class _ActionItemResult(BaseModel):
    items: list[_ActionItem]

class _FillInBlankItem(BaseModel):
    sentence: str
    answer: str
    hint: str = ""
    starred: bool = False

class _FillInBlankResult(BaseModel):
    items: list[_FillInBlankItem]

class _TrueFalseItem(BaseModel):
    statement: str
    is_true: bool
    explanation: str = ""
    starred: bool = False

class _TrueFalseResult(BaseModel):
    items: list[_TrueFalseItem]

class _ErrorDetectionItem(BaseModel):
    statement: str
    error: str
    correction: str
    explanation: str = ""
    starred: bool = False

class _ErrorDetectionResult(BaseModel):
    items: list[_ErrorDetectionItem]


# ---------------------------------------------------------------------------
# System instructions (describe content, not format — PydanticAI enforces schema)
# ---------------------------------------------------------------------------

_SUMMARY_INSTRUCTIONS = (
    "You are an expert academic assistant. Given a class or lecture transcript, "
    "write a clear executive summary of 200-400 words covering the main topics, "
    "key takeaways, and overall purpose of the session. "
    "Return ONLY the plain summary text, no markdown headers, no extra commentary."
)

_QA_INSTRUCTIONS = (
    "You are an expert academic assistant. Given a class or lecture transcript, "
    "create exactly 10 question-answer pairs covering the most important concepts. "
    "Set starred=true for topics the professor explicitly signals as especially important "
    "(e.g. 'this will be on the exam', 'very important', 'key concept', 'pay attention to this')."
)

_FLASHCARD_INSTRUCTIONS = (
    "You are an expert academic assistant. Given a class or lecture transcript, "
    "create exactly 20 flashcard pairs for the key concepts introduced. "
    "Set starred=true for concepts the professor explicitly signals as especially important."
)

_ACTION_ITEMS_INSTRUCTIONS = (
    "You are an expert academic assistant. Given a class or lecture transcript, "
    "extract all action items: assignments, deadlines, homework, tasks, and urgent notices. "
    "Classify urgency as high/medium/low. Include extracted_date when a specific date or "
    "deadline was mentioned; otherwise leave it null."
)

_FILL_IN_BLANK_INSTRUCTIONS = (
    "You are an expert academic assistant. Given a class or lecture transcript, "
    "create exactly 10 fill-in-the-blank items targeting key concepts and terminology. "
    "Replace the key term in the sentence with ___. "
    "Set starred=true for concepts the professor explicitly signals as especially important."
)

_TRUE_FALSE_INSTRUCTIONS = (
    "You are an expert academic assistant. Given a class or lecture transcript, "
    "create exactly 15 true-or-false statements. Make roughly half true and half false. "
    "False statements should be subtly wrong (changed number, swapped concept, wrong relationship). "
    "Set starred=true for topics the professor explicitly signals as especially important."
)

_ERROR_DETECTION_INSTRUCTIONS = (
    "You are an expert academic assistant. Given a class or lecture transcript, "
    "create exactly 10 error-detection items. Each is a statement with exactly ONE deliberate "
    "factual error — a wrong term, incorrect number, swapped concept, or false relationship. "
    "Set starred=true for topics the professor explicitly signals as especially important."
)


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

async def generate_summary(transcript: str) -> str:
    """Generate a 200-400 word executive summary. Returns '' on failure."""
    if not transcript or not transcript.strip():
        return ""
    if not _has_api_key():
        logger.warning("No AI API key set; skipping summary generation")
        return ""
    try:
        import anthropic as _anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        client = _anthropic.AsyncAnthropic(api_key=api_key)
        msg = await client.messages.create(
            model=os.environ.get("AI_MODEL", "claude-sonnet-4-6"),
            max_tokens=1024,
            system=_SUMMARY_INSTRUCTIONS,
            messages=[{"role": "user", "content": transcript}],
        )
        return msg.content[0].text.strip()
    except Exception as exc:
        logger.warning("Summary generation failed: %s", exc)
        return ""


async def generate_qa_pairs(transcript: str) -> list[dict]:
    """Generate 10 Q&A pairs. Each dict: question, answer, starred. Returns [] on failure."""
    if not transcript or not transcript.strip():
        return []
    if not _has_api_key():
        logger.warning("No AI API key set; skipping Q&A generation")
        return []
    try:
        agent: Agent[None, _QAResult] = Agent(
            _get_model(), output_type=_QAResult, instructions=_QA_INSTRUCTIONS
        )
        result = await agent.run(transcript)
        return [item.model_dump() for item in result.output.pairs]
    except Exception as exc:
        logger.warning("Q&A generation failed: %s", exc)
        return []


async def generate_flashcards(transcript: str) -> list[dict]:
    """Generate 20 flashcards. Each dict: concept, definition, starred. Returns [] on failure."""
    if not transcript or not transcript.strip():
        return []
    if not _has_api_key():
        logger.warning("No AI API key set; skipping flashcard generation")
        return []
    try:
        agent: Agent[None, _FlashcardResult] = Agent(
            _get_model(), output_type=_FlashcardResult, instructions=_FLASHCARD_INSTRUCTIONS
        )
        result = await agent.run(transcript)
        return [item.model_dump() for item in result.output.cards]
    except Exception as exc:
        logger.warning("Flashcard generation failed: %s", exc)
        return []


async def generate_action_items(transcript: str) -> list[dict]:
    """Extract action items. Each dict: text, urgency, extracted_date. Returns [] on failure."""
    if not transcript or not transcript.strip():
        return []
    if not _has_api_key():
        logger.warning("No AI API key set; skipping action items generation")
        return []
    try:
        agent: Agent[None, _ActionItemResult] = Agent(
            _get_model(), output_type=_ActionItemResult, instructions=_ACTION_ITEMS_INSTRUCTIONS
        )
        result = await agent.run(transcript)
        return [item.model_dump() for item in result.output.items]
    except Exception as exc:
        logger.warning("Action items generation failed: %s", exc)
        return []


async def generate_fill_in_blank(transcript: str) -> list[dict]:
    """Generate 10 fill-in-blank items. Each dict: sentence, answer, hint, starred. Returns [] on failure."""
    if not transcript or not transcript.strip():
        return []
    if not _has_api_key():
        logger.warning("No AI API key set; skipping fill-in-blank generation")
        return []
    try:
        agent: Agent[None, _FillInBlankResult] = Agent(
            _get_model(), output_type=_FillInBlankResult, instructions=_FILL_IN_BLANK_INSTRUCTIONS
        )
        result = await agent.run(transcript)
        return [item.model_dump() for item in result.output.items]
    except Exception as exc:
        logger.warning("Fill-in-blank generation failed: %s", exc)
        return []


async def generate_true_false(transcript: str) -> list[dict]:
    """Generate 15 true/false items. Each dict: statement, is_true, explanation, starred. Returns [] on failure."""
    if not transcript or not transcript.strip():
        return []
    if not _has_api_key():
        logger.warning("No AI API key set; skipping true/false generation")
        return []
    try:
        agent: Agent[None, _TrueFalseResult] = Agent(
            _get_model(), output_type=_TrueFalseResult, instructions=_TRUE_FALSE_INSTRUCTIONS
        )
        result = await agent.run(transcript)
        return [item.model_dump() for item in result.output.items]
    except Exception as exc:
        logger.warning("True/false generation failed: %s", exc)
        return []


async def generate_error_detection(transcript: str) -> list[dict]:
    """Generate 10 error-detection items. Each dict: statement, error, correction, explanation, starred. Returns [] on failure."""
    if not transcript or not transcript.strip():
        return []
    if not _has_api_key():
        logger.warning("No AI API key set; skipping error detection generation")
        return []
    try:
        agent: Agent[None, _ErrorDetectionResult] = Agent(
            _get_model(), output_type=_ErrorDetectionResult, instructions=_ERROR_DETECTION_INSTRUCTIONS
        )
        result = await agent.run(transcript)
        return [item.model_dump() for item in result.output.items]
    except Exception as exc:
        logger.warning("Error detection generation failed: %s", exc)
        return []


async def generate_all(transcript: str) -> dict:
    """Run all 7 generators and return a combined result dict."""
    summary, qa_pairs, flashcards, action_items, fill_in_blank, true_false, error_detection = (
        await generate_summary(transcript),
        await generate_qa_pairs(transcript),
        await generate_flashcards(transcript),
        await generate_action_items(transcript),
        await generate_fill_in_blank(transcript),
        await generate_true_false(transcript),
        await generate_error_detection(transcript),
    )
    return {
        "summary": summary,
        "qa_pairs": qa_pairs,
        "flashcards": flashcards,
        "action_items": action_items,
        "fill_in_blank": fill_in_blank,
        "true_false": true_false,
        "error_detection": error_detection,
    }
