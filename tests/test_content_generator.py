"""Tests for services/content_generator.py.

All tests mock the Anthropic client so no real API key is required.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tui_transcript.services import content_generator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_client(response_text: str) -> MagicMock:
    """Return a mock AsyncAnthropic client whose messages.create returns response_text."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=response_text)]

    mock_messages = MagicMock()
    mock_messages.create = AsyncMock(return_value=mock_msg)

    mock_client = MagicMock()
    mock_client.messages = mock_messages
    return mock_client


SAMPLE_TRANSCRIPT = (
    "Today we discussed Newton's laws of motion. "
    "The first law states that an object at rest stays at rest. "
    "Homework: read chapter 3 by Friday May 9th. "
    "The second law relates force, mass and acceleration."
)


# ---------------------------------------------------------------------------
# generate_summary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_summary_returns_text(monkeypatch):
    mock_client = _make_mock_client("This lecture covered Newton's laws.")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await content_generator.generate_summary(SAMPLE_TRANSCRIPT)

    assert result == "This lecture covered Newton's laws."
    mock_client.messages.create.assert_awaited_once()
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == content_generator._MODEL
    assert call_kwargs["system"] == content_generator._SUMMARY_SYSTEM


@pytest.mark.asyncio
async def test_generate_summary_empty_transcript():
    result = await content_generator.generate_summary("")
    assert result == ""


@pytest.mark.asyncio
async def test_generate_summary_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = await content_generator.generate_summary(SAMPLE_TRANSCRIPT)
    assert result == ""


# ---------------------------------------------------------------------------
# generate_qa_pairs
# ---------------------------------------------------------------------------

_QA_JSON = json.dumps([
    {"question": "What is Newton's first law?", "answer": "An object at rest stays at rest.", "starred": False},
    {"question": "What is inertia?", "answer": "Resistance to change in motion.", "starred": True},
])


@pytest.mark.asyncio
async def test_generate_qa_pairs_parses_json(monkeypatch):
    mock_client = _make_mock_client(_QA_JSON)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
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
async def test_generate_qa_pairs_filters_invalid_items(monkeypatch):
    # One item is missing 'answer' — should be filtered out
    bad_json = json.dumps([
        {"question": "What is inertia?", "answer": "Resistance to change."},
        {"question": "Missing answer only"},
        {"not_a_question": "irrelevant"},
    ])
    mock_client = _make_mock_client(bad_json)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await content_generator.generate_qa_pairs(SAMPLE_TRANSCRIPT)

    assert len(result) == 1
    assert result[0]["question"] == "What is inertia?"


@pytest.mark.asyncio
async def test_generate_qa_pairs_handles_invalid_json(monkeypatch):
    mock_client = _make_mock_client("not valid json at all")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await content_generator.generate_qa_pairs(SAMPLE_TRANSCRIPT)

    assert result == []


@pytest.mark.asyncio
async def test_generate_qa_pairs_empty_transcript():
    result = await content_generator.generate_qa_pairs("")
    assert result == []


# ---------------------------------------------------------------------------
# generate_flashcards
# ---------------------------------------------------------------------------

_FLASHCARD_JSON = json.dumps([
    {"concept": "Newton's First Law", "definition": "An object at rest stays at rest unless acted on.", "starred": True},
    {"concept": "Inertia", "definition": "The resistance of an object to changes in its state of motion.", "starred": False},
])


@pytest.mark.asyncio
async def test_generate_flashcards_parses_json(monkeypatch):
    mock_client = _make_mock_client(_FLASHCARD_JSON)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await content_generator.generate_flashcards(SAMPLE_TRANSCRIPT)

    assert len(result) == 2
    assert result[0]["concept"] == "Newton's First Law"
    assert result[0]["starred"] is True
    assert "resistance" in result[1]["definition"].lower()
    assert result[1]["starred"] is False


@pytest.mark.asyncio
async def test_generate_flashcards_filters_invalid_items(monkeypatch):
    bad_json = json.dumps([
        {"concept": "Inertia", "definition": "Resistance to change."},
        {"concept": "No definition here"},
    ])
    mock_client = _make_mock_client(bad_json)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await content_generator.generate_flashcards(SAMPLE_TRANSCRIPT)

    assert len(result) == 1


@pytest.mark.asyncio
async def test_generate_flashcards_empty_transcript():
    result = await content_generator.generate_flashcards("")
    assert result == []


# ---------------------------------------------------------------------------
# generate_action_items
# ---------------------------------------------------------------------------

_ACTION_JSON = json.dumps([
    {"text": "Read chapter 3", "urgency": "high", "extracted_date": "May 9th"},
    {"text": "Submit lab report", "urgency": "medium", "extracted_date": None},
])


@pytest.mark.asyncio
async def test_generate_action_items_parses_json(monkeypatch):
    mock_client = _make_mock_client(_ACTION_JSON)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await content_generator.generate_action_items(SAMPLE_TRANSCRIPT)

    assert len(result) == 2
    assert result[0] == {"text": "Read chapter 3", "urgency": "high", "extracted_date": "May 9th"}
    assert result[1]["extracted_date"] is None
    assert result[1]["urgency"] == "medium"


@pytest.mark.asyncio
async def test_generate_action_items_defaults_missing_urgency(monkeypatch):
    json_no_urgency = json.dumps([
        {"text": "Do homework"},  # no urgency field
    ])
    mock_client = _make_mock_client(json_no_urgency)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await content_generator.generate_action_items(SAMPLE_TRANSCRIPT)

    assert result[0]["urgency"] == "medium"
    assert result[0]["extracted_date"] is None


@pytest.mark.asyncio
async def test_generate_action_items_empty_transcript():
    result = await content_generator.generate_action_items("")
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
    ):
        result = await content_generator.generate_all(SAMPLE_TRANSCRIPT)

    assert result["summary"] == "summary text"
    assert result["qa_pairs"] == [{"question": "Q1", "answer": "A1"}]
    assert result["flashcards"] == [{"concept": "C1", "definition": "D1"}]
    assert result["action_items"] == [{"text": "Do X", "urgency": "high", "extracted_date": None}]
    assert set(result.keys()) == {"summary", "qa_pairs", "flashcards", "action_items"}


@pytest.mark.asyncio
async def test_generate_all_empty_transcript():
    result = await content_generator.generate_all("")
    assert result == {"summary": "", "qa_pairs": [], "flashcards": [], "action_items": []}


# ---------------------------------------------------------------------------
# starred field behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_qa_pairs_starred_defaults_to_false(monkeypatch):
    """Items missing the 'starred' field should default to False."""
    json_without_starred = json.dumps([
        {"question": "What is gravity?", "answer": "A fundamental force."},
    ])
    mock_client = _make_mock_client(json_without_starred)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await content_generator.generate_qa_pairs(SAMPLE_TRANSCRIPT)

    assert len(result) == 1
    assert result[0]["starred"] is False


@pytest.mark.asyncio
async def test_generate_qa_pairs_starred_true_when_set(monkeypatch):
    """Items with starred=true should have starred=True in the result."""
    json_with_starred = json.dumps([
        {"question": "This is on the exam?", "answer": "Yes.", "starred": True},
        {"question": "Normal question?", "answer": "Normal answer.", "starred": False},
    ])
    mock_client = _make_mock_client(json_with_starred)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await content_generator.generate_qa_pairs(SAMPLE_TRANSCRIPT)

    assert result[0]["starred"] is True
    assert result[1]["starred"] is False


@pytest.mark.asyncio
async def test_generate_flashcards_starred_defaults_to_false(monkeypatch):
    """Flashcard items missing the 'starred' field should default to False."""
    json_without_starred = json.dumps([
        {"concept": "Entropy", "definition": "Measure of disorder."},
    ])
    mock_client = _make_mock_client(json_without_starred)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await content_generator.generate_flashcards(SAMPLE_TRANSCRIPT)

    assert len(result) == 1
    assert result[0]["starred"] is False


@pytest.mark.asyncio
async def test_generate_flashcards_starred_true_when_set(monkeypatch):
    """Flashcard items with starred=true should have starred=True in the result."""
    json_with_starred = json.dumps([
        {"concept": "Key theorem", "definition": "Pay attention to this.", "starred": True},
        {"concept": "Other concept", "definition": "Less critical.", "starred": False},
    ])
    mock_client = _make_mock_client(json_with_starred)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await content_generator.generate_flashcards(SAMPLE_TRANSCRIPT)

    assert result[0]["starred"] is True
    assert result[1]["starred"] is False
