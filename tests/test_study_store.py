"""Tests for StudyStore save/get round trips."""

from __future__ import annotations

from pathlib import Path

import pytest

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.study_store import StudyStore
from tests.conftest import _insert_video


@pytest.fixture()
def db(tmp_path: Path) -> HistoryDB:
    db = HistoryDB(tmp_path / "test_study.db")
    yield db
    db.close()


@pytest.fixture()
def store(db: HistoryDB) -> StudyStore:
    s = StudyStore(db=db)
    yield s


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

class TestSummaries:
    def test_save_and_get(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        row_id = store.save_summary(vid, "A concise summary.")
        assert isinstance(row_id, int)
        result = store.get_summary(vid)
        assert result is not None
        assert result["text"] == "A concise summary."
        assert result["video_id"] == vid

    def test_get_returns_none_for_unknown_video(self, store: StudyStore) -> None:
        assert store.get_summary(9999) is None

    def test_save_replaces_existing(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.save_summary(vid, "First version.")
        store.save_summary(vid, "Updated version.")
        result = store.get_summary(vid)
        assert result is not None
        assert result["text"] == "Updated version."

    def test_generated_at_is_populated(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.save_summary(vid, "Some text.")
        result = store.get_summary(vid)
        assert result["generated_at"] is not None

    def test_user_id_nullable(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.save_summary(vid, "Text.")
        result = store.get_summary(vid)
        assert result["user_id"] is None


# ---------------------------------------------------------------------------
# Q&A pairs
# ---------------------------------------------------------------------------

class TestQAPairs:
    def test_save_and_get(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        pairs = [
            {"question": "What is ML?", "answer": "Machine Learning."},
            {"question": "What is DL?", "answer": "Deep Learning."},
        ]
        store.save_qa_pairs(vid, pairs)
        result = store.get_qa_pairs(vid)
        assert len(result) == 2
        assert result[0]["question"] == "What is ML?"
        assert result[1]["answer"] == "Deep Learning."

    def test_sort_order_is_preserved(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        pairs = [{"question": f"Q{i}", "answer": f"A{i}"} for i in range(5)]
        store.save_qa_pairs(vid, pairs)
        result = store.get_qa_pairs(vid)
        for i, item in enumerate(result):
            assert item["sort_order"] == i

    def test_get_empty_for_unknown_video(self, store: StudyStore) -> None:
        assert store.get_qa_pairs(9999) == []

    def test_save_replaces_existing(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.save_qa_pairs(vid, [{"question": "Old Q", "answer": "Old A"}])
        store.save_qa_pairs(vid, [{"question": "New Q", "answer": "New A"}])
        result = store.get_qa_pairs(vid)
        assert len(result) == 1
        assert result[0]["question"] == "New Q"

    def test_user_id_nullable(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.save_qa_pairs(vid, [{"question": "Q", "answer": "A"}])
        result = store.get_qa_pairs(vid)
        assert result[0]["user_id"] is None

    def test_starred_defaults_to_false(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.save_qa_pairs(vid, [{"question": "Q", "answer": "A"}])
        result = store.get_qa_pairs(vid)
        assert result[0]["starred"] is False

    def test_starred_true_is_persisted(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        pairs = [
            {"question": "Exam Q", "answer": "Exam A", "starred": True},
            {"question": "Normal Q", "answer": "Normal A", "starred": False},
        ]
        store.save_qa_pairs(vid, pairs)
        result = store.get_qa_pairs(vid)
        assert result[0]["starred"] is True
        assert result[1]["starred"] is False


# ---------------------------------------------------------------------------
# Flashcards
# ---------------------------------------------------------------------------

class TestFlashcards:
    def test_save_and_get(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        cards = [
            {"concept": "Gradient Descent", "definition": "Optimisation algorithm."},
            {"concept": "Backpropagation", "definition": "Compute gradients via chain rule."},
        ]
        store.save_flashcards(vid, cards)
        result = store.get_flashcards(vid)
        assert len(result) == 2
        assert result[0]["concept"] == "Gradient Descent"
        assert result[1]["definition"] == "Compute gradients via chain rule."

    def test_sort_order_is_preserved(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        cards = [{"concept": f"C{i}", "definition": f"D{i}"} for i in range(4)]
        store.save_flashcards(vid, cards)
        result = store.get_flashcards(vid)
        for i, card in enumerate(result):
            assert card["sort_order"] == i

    def test_get_empty_for_unknown_video(self, store: StudyStore) -> None:
        assert store.get_flashcards(9999) == []

    def test_save_replaces_existing(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.save_flashcards(vid, [{"concept": "Old", "definition": "Old def"}])
        store.save_flashcards(vid, [{"concept": "New", "definition": "New def"}])
        result = store.get_flashcards(vid)
        assert len(result) == 1
        assert result[0]["concept"] == "New"

    def test_user_id_nullable(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.save_flashcards(vid, [{"concept": "C", "definition": "D"}])
        result = store.get_flashcards(vid)
        assert result[0]["user_id"] is None

    def test_starred_defaults_to_false(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.save_flashcards(vid, [{"concept": "C", "definition": "D"}])
        result = store.get_flashcards(vid)
        assert result[0]["starred"] is False

    def test_starred_true_is_persisted(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        cards = [
            {"concept": "Key Concept", "definition": "Very important.", "starred": True},
            {"concept": "Other", "definition": "Less critical.", "starred": False},
        ]
        store.save_flashcards(vid, cards)
        result = store.get_flashcards(vid)
        assert result[0]["starred"] is True
        assert result[1]["starred"] is False


# ---------------------------------------------------------------------------
# Action items
# ---------------------------------------------------------------------------

class TestActionItems:
    def test_save_and_get(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        items = [
            {"text": "Review chapter 3", "urgency": "high", "extracted_date": "2026-05-01"},
            {"text": "Do exercises", "urgency": "low"},
        ]
        store.save_action_items(vid, items)
        result = store.get_action_items(vid)
        assert len(result) == 2
        assert result[0]["text"] == "Review chapter 3"
        assert result[0]["urgency"] == "high"
        assert result[0]["extracted_date"] == "2026-05-01"
        assert result[1]["extracted_date"] is None

    def test_urgency_values(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        for urgency in ("high", "medium", "low"):
            store.save_action_items(vid, [{"text": "Task", "urgency": urgency}])
            result = store.get_action_items(vid)
            assert result[0]["urgency"] == urgency

    def test_dismissed_defaults_to_false(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.save_action_items(vid, [{"text": "Task", "urgency": "medium"}])
        result = store.get_action_items(vid)
        assert result[0]["dismissed"] is False

    def test_dismiss_action_item(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.save_action_items(vid, [{"text": "Task", "urgency": "high"}])
        item = store.get_action_items(vid)[0]
        store.dismiss_action_item(item["id"])
        result = store.get_action_items(vid)
        assert result[0]["dismissed"] is True

    def test_get_empty_for_unknown_video(self, store: StudyStore) -> None:
        assert store.get_action_items(9999) == []

    def test_save_replaces_existing(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.save_action_items(vid, [{"text": "Old task", "urgency": "low"}])
        store.save_action_items(vid, [{"text": "New task", "urgency": "high"}])
        result = store.get_action_items(vid)
        assert len(result) == 1
        assert result[0]["text"] == "New task"

    def test_created_at_is_populated(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.save_action_items(vid, [{"text": "Task", "urgency": "medium"}])
        result = store.get_action_items(vid)
        assert result[0]["created_at"] is not None

    def test_user_id_nullable(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.save_action_items(vid, [{"text": "Task", "urgency": "low"}])
        result = store.get_action_items(vid)
        assert result[0]["user_id"] is None


# ---------------------------------------------------------------------------
# get_all_alerts
# ---------------------------------------------------------------------------

class TestGetAllAlerts:
    def test_returns_only_undismissed_by_default(
        self, store: StudyStore, db: HistoryDB
    ) -> None:
        vid1 = _insert_video(db, 1)
        vid2 = _insert_video(db, 2)
        store.save_action_items(vid1, [{"text": "Task A", "urgency": "high"}])
        store.save_action_items(vid2, [{"text": "Task B", "urgency": "low"}])
        # Dismiss task from vid1
        item_a = store.get_action_items(vid1)[0]
        store.dismiss_action_item(item_a["id"])

        alerts = store.get_all_alerts()
        assert len(alerts) == 1
        assert alerts[0]["text"] == "Task B"

    def test_dismissed_true_includes_all(
        self, store: StudyStore, db: HistoryDB
    ) -> None:
        vid = _insert_video(db, 1)
        store.save_action_items(
            vid,
            [
                {"text": "Task A", "urgency": "high"},
                {"text": "Task B", "urgency": "low"},
            ],
        )
        item = store.get_action_items(vid)[0]
        store.dismiss_action_item(item["id"])

        alerts = store.get_all_alerts(dismissed=True)
        assert len(alerts) == 2

    def test_includes_video_id(self, store: StudyStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.save_action_items(vid, [{"text": "Task", "urgency": "medium"}])
        alerts = store.get_all_alerts()
        assert alerts[0]["video_id"] == vid

    def test_empty_when_no_items(self, store: StudyStore) -> None:
        assert store.get_all_alerts() == []
