"""Tests for services/content_generator.py.

Summary generation still uses the raw Anthropic SDK and is tested by mocking
``anthropic.AsyncAnthropic``. All other generators use PydanticAI ``Agent``
objects, which are mocked at the import site so the real LLM is never called.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tui_transcript.services import content_generator
from tui_transcript.services.content_generator import (
    _ActionItem,
    _ActionItemResult,
    _ErrorDetectionItem,
    _ErrorDetectionResult,
    _FillInBlankItem,
    _FillInBlankResult,
    _FlashcardItem,
    _FlashcardResult,
    _QAItem,
    _QAResult,
    _TrueFalseItem,
    _TrueFalseResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_anthropic_client(response_text: str) -> MagicMock:
    """Mock AsyncAnthropic whose messages.create returns response_text."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=response_text)]

    mock_messages = MagicMock()
    mock_messages.create = AsyncMock(return_value=mock_msg)

    mock_client = MagicMock()
    mock_client.messages = mock_messages
    return mock_client


def _mock_agent(output_obj) -> MagicMock:
    """Mock instance returned by Agent(...) — agent.run() resolves to AgentRunResult-like with .output=output_obj."""
    run_result = MagicMock()
    run_result.output = output_obj
    agent_instance = MagicMock()
    agent_instance.run = AsyncMock(return_value=run_result)
    return agent_instance


def _patch_agent(output_obj):
    """Context manager that patches Agent in the content_generator module."""
    return patch(
        "tui_transcript.services.content_generator.Agent",
        return_value=_mock_agent(output_obj),
    )


def _patch_agent_failing(exc: Exception):
    """Patch Agent so its .run raises the given exception — exercises the empty-on-failure path."""
    failing = MagicMock()
    failing.run = AsyncMock(side_effect=exc)
    return patch(
        "tui_transcript.services.content_generator.Agent",
        return_value=failing,
    )


SAMPLE_TRANSCRIPT = (
    "Today we discussed Newton's laws of motion. "
    "The first law states that an object at rest stays at rest. "
    "Homework: read chapter 3 by Friday May 9th. "
    "The second law relates force, mass and acceleration."
)


# ---------------------------------------------------------------------------
# generate_summary (raw Anthropic SDK)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_summary_returns_text(monkeypatch):
    mock_client = _make_mock_anthropic_client("This lecture covered Newton's laws.")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("AI_PROVIDER", raising=False)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await content_generator.generate_summary(SAMPLE_TRANSCRIPT)

    assert result == "This lecture covered Newton's laws."
    mock_client.messages.create.assert_awaited_once()
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert call_kwargs["system"] == content_generator._SUMMARY_INSTRUCTIONS


@pytest.mark.asyncio
async def test_generate_summary_empty_transcript():
    result = await content_generator.generate_summary("")
    assert result == ""


@pytest.mark.asyncio
async def test_generate_summary_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    result = await content_generator.generate_summary(SAMPLE_TRANSCRIPT)
    assert result == ""


# ---------------------------------------------------------------------------
# _get_model
# ---------------------------------------------------------------------------

def test_get_model_defaults_to_anthropic(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    assert content_generator._get_model() == "anthropic:claude-sonnet-4-6"


def test_get_model_openai(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.delenv("AI_MODEL", raising=False)
    assert content_generator._get_model() == "openai:gpt-4o"


def test_get_model_google(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "google")
    monkeypatch.delenv("AI_MODEL", raising=False)
    assert content_generator._get_model() == "google-gla:gemini-2.0-flash"


def test_get_model_respects_ai_model_override(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("AI_MODEL", "claude-haiku-4-5-20251001")
    assert content_generator._get_model() == "anthropic:claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# generate_qa_pairs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_qa_pairs_returns_dicts(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    output = _QAResult(pairs=[
        _QAItem(question="What is Newton's first law?", answer="An object at rest stays at rest.", starred=False),
        _QAItem(question="What is inertia?", answer="Resistance to change in motion.", starred=True),
    ])

    with _patch_agent(output):
        result = await content_generator.generate_qa_pairs(SAMPLE_TRANSCRIPT)

    assert len(result) == 2
    assert result[0] == {
        "question": "What is Newton's first law?",
        "answer": "An object at rest stays at rest.",
        "starred": False,
    }
    assert result[1]["answer"] == "Resistance to change in motion."
    assert result[1]["starred"] is True


@pytest.mark.asyncio
async def test_generate_qa_pairs_starred_defaults_to_false(monkeypatch):
    """Items omitting ``starred`` should fall back to the Pydantic default of False."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    # Build the item without supplying starred — the Pydantic default takes over.
    output = _QAResult(pairs=[_QAItem(question="What is gravity?", answer="A fundamental force.")])

    with _patch_agent(output):
        result = await content_generator.generate_qa_pairs(SAMPLE_TRANSCRIPT)

    assert len(result) == 1
    assert result[0]["starred"] is False


@pytest.mark.asyncio
async def test_generate_qa_pairs_handles_agent_failure(monkeypatch):
    """If the agent.run raises, the function logs and returns []."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with _patch_agent_failing(RuntimeError("model failed validation")):
        result = await content_generator.generate_qa_pairs(SAMPLE_TRANSCRIPT)
    assert result == []


@pytest.mark.asyncio
async def test_generate_qa_pairs_empty_transcript():
    result = await content_generator.generate_qa_pairs("")
    assert result == []


@pytest.mark.asyncio
async def test_generate_qa_pairs_no_api_key(monkeypatch):
    """No API key for the configured provider → empty result, no agent constructed."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    with patch("tui_transcript.services.content_generator.Agent") as MockAgent:
        result = await content_generator.generate_qa_pairs(SAMPLE_TRANSCRIPT)
    assert result == []
    MockAgent.assert_not_called()


# ---------------------------------------------------------------------------
# generate_flashcards
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_flashcards_returns_dicts(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    output = _FlashcardResult(cards=[
        _FlashcardItem(concept="Newton's First Law", definition="An object at rest stays at rest unless acted on.", starred=True),
        _FlashcardItem(concept="Inertia", definition="The resistance of an object to changes in motion.", starred=False),
    ])

    with _patch_agent(output):
        result = await content_generator.generate_flashcards(SAMPLE_TRANSCRIPT)

    assert len(result) == 2
    assert result[0]["concept"] == "Newton's First Law"
    assert result[0]["starred"] is True
    assert "resistance" in result[1]["definition"].lower()
    assert result[1]["starred"] is False


@pytest.mark.asyncio
async def test_generate_flashcards_starred_defaults_to_false(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    output = _FlashcardResult(cards=[_FlashcardItem(concept="Entropy", definition="Measure of disorder.")])

    with _patch_agent(output):
        result = await content_generator.generate_flashcards(SAMPLE_TRANSCRIPT)

    assert len(result) == 1
    assert result[0]["starred"] is False


@pytest.mark.asyncio
async def test_generate_flashcards_empty_transcript():
    result = await content_generator.generate_flashcards("")
    assert result == []


# ---------------------------------------------------------------------------
# generate_action_items
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_action_items_returns_dicts(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    output = _ActionItemResult(items=[
        _ActionItem(text="Read chapter 3", urgency="high", extracted_date="May 9th"),
        _ActionItem(text="Submit lab report", urgency="medium", extracted_date=None),
    ])

    with _patch_agent(output):
        result = await content_generator.generate_action_items(SAMPLE_TRANSCRIPT)

    assert len(result) == 2
    assert result[0] == {"text": "Read chapter 3", "urgency": "high", "extracted_date": "May 9th"}
    assert result[1]["extracted_date"] is None
    assert result[1]["urgency"] == "medium"


@pytest.mark.asyncio
async def test_generate_action_items_defaults_missing_urgency(monkeypatch):
    """The Pydantic default urgency is 'medium' when omitted."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    output = _ActionItemResult(items=[_ActionItem(text="Do homework")])

    with _patch_agent(output):
        result = await content_generator.generate_action_items(SAMPLE_TRANSCRIPT)

    assert result[0]["urgency"] == "medium"
    assert result[0]["extracted_date"] is None


@pytest.mark.asyncio
async def test_generate_action_items_empty_transcript():
    result = await content_generator.generate_action_items("")
    assert result == []


# ---------------------------------------------------------------------------
# generate_fill_in_blank
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_fill_in_blank_returns_dicts(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    output = _FillInBlankResult(items=[
        _FillInBlankItem(sentence="The ___ is the resistance to change.", answer="inertia", hint="starts with i", starred=True),
    ])

    with _patch_agent(output):
        result = await content_generator.generate_fill_in_blank(SAMPLE_TRANSCRIPT)

    assert len(result) == 1
    assert result[0] == {
        "sentence": "The ___ is the resistance to change.",
        "answer": "inertia",
        "hint": "starts with i",
        "starred": True,
    }


@pytest.mark.asyncio
async def test_generate_fill_in_blank_empty_transcript():
    result = await content_generator.generate_fill_in_blank("")
    assert result == []


# ---------------------------------------------------------------------------
# generate_true_false
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_true_false_returns_dicts(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    output = _TrueFalseResult(items=[
        _TrueFalseItem(statement="Newton's first law is about inertia.", is_true=True, explanation="Correct.", starred=False),
        _TrueFalseItem(statement="F=mv.", is_true=False, explanation="It's F=ma.", starred=True),
    ])

    with _patch_agent(output):
        result = await content_generator.generate_true_false(SAMPLE_TRANSCRIPT)

    assert len(result) == 2
    assert result[0]["is_true"] is True
    assert result[1]["is_true"] is False
    assert result[1]["starred"] is True


@pytest.mark.asyncio
async def test_generate_true_false_empty_transcript():
    result = await content_generator.generate_true_false("")
    assert result == []


# ---------------------------------------------------------------------------
# generate_error_detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_error_detection_returns_dicts(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    output = _ErrorDetectionResult(items=[
        _ErrorDetectionItem(
            statement="Newton's second law relates force and velocity.",
            error="velocity",
            correction="acceleration",
            explanation="F=ma involves acceleration, not velocity.",
            starred=False,
        ),
        _ErrorDetectionItem(
            statement="The third law states action and reaction are unequal.",
            error="unequal",
            correction="equal",
            explanation="Action and reaction forces are always equal in magnitude.",
            starred=True,
        ),
    ])

    with _patch_agent(output):
        result = await content_generator.generate_error_detection(SAMPLE_TRANSCRIPT)

    assert len(result) == 2
    assert result[0] == {
        "statement": "Newton's second law relates force and velocity.",
        "error": "velocity",
        "correction": "acceleration",
        "explanation": "F=ma involves acceleration, not velocity.",
        "starred": False,
    }
    assert result[1]["correction"] == "equal"
    assert result[1]["starred"] is True


@pytest.mark.asyncio
async def test_generate_error_detection_starred_defaults_to_false(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    output = _ErrorDetectionResult(items=[
        _ErrorDetectionItem(statement="Some statement.", error="error", correction="fix", explanation="Explanation."),
    ])

    with _patch_agent(output):
        result = await content_generator.generate_error_detection(SAMPLE_TRANSCRIPT)

    assert result[0]["starred"] is False


@pytest.mark.asyncio
async def test_generate_error_detection_handles_agent_failure(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with _patch_agent_failing(ValueError("invalid")):
        result = await content_generator.generate_error_detection(SAMPLE_TRANSCRIPT)
    assert result == []


@pytest.mark.asyncio
async def test_generate_error_detection_empty_transcript():
    result = await content_generator.generate_error_detection("")
    assert result == []


# ---------------------------------------------------------------------------
# generate_all
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_all_returns_combined_dict(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with (
        patch.object(content_generator, "generate_summary", new=AsyncMock(return_value="summary text")),
        patch.object(content_generator, "generate_qa_pairs", new=AsyncMock(return_value=[{"question": "Q1", "answer": "A1"}])),
        patch.object(content_generator, "generate_flashcards", new=AsyncMock(return_value=[{"concept": "C1", "definition": "D1"}])),
        patch.object(content_generator, "generate_action_items", new=AsyncMock(return_value=[{"text": "Do X", "urgency": "high", "extracted_date": None}])),
        patch.object(content_generator, "generate_fill_in_blank", new=AsyncMock(return_value=[{"sentence": "The ___ is key.", "answer": "concept", "hint": "", "starred": False}])),
        patch.object(content_generator, "generate_true_false", new=AsyncMock(return_value=[{"statement": "Newton's first law is about inertia.", "is_true": True, "explanation": "Correct.", "starred": False}])),
        patch.object(content_generator, "generate_error_detection", new=AsyncMock(return_value=[{"statement": "Newton's second law relates force and velocity.", "error": "velocity", "correction": "acceleration", "explanation": "F=ma involves acceleration.", "starred": False}])),
    ):
        result = await content_generator.generate_all(SAMPLE_TRANSCRIPT)

    assert result["summary"] == "summary text"
    assert result["qa_pairs"] == [{"question": "Q1", "answer": "A1"}]
    assert result["flashcards"] == [{"concept": "C1", "definition": "D1"}]
    assert result["action_items"] == [{"text": "Do X", "urgency": "high", "extracted_date": None}]
    assert result["fill_in_blank"] == [{"sentence": "The ___ is key.", "answer": "concept", "hint": "", "starred": False}]
    assert result["true_false"] == [{"statement": "Newton's first law is about inertia.", "is_true": True, "explanation": "Correct.", "starred": False}]
    assert result["error_detection"] == [{"statement": "Newton's second law relates force and velocity.", "error": "velocity", "correction": "acceleration", "explanation": "F=ma involves acceleration.", "starred": False}]
    assert set(result.keys()) == {"summary", "qa_pairs", "flashcards", "action_items", "fill_in_blank", "true_false", "error_detection"}


@pytest.mark.asyncio
async def test_generate_all_empty_transcript():
    result = await content_generator.generate_all("")
    assert result == {
        "summary": "",
        "qa_pairs": [],
        "flashcards": [],
        "action_items": [],
        "fill_in_blank": [],
        "true_false": [],
        "error_detection": [],
    }
