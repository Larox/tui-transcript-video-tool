"""Service for accessing generated study content (summaries, Q&A, flashcards, action items)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from tui_transcript.services.history import DB_PATH, HistoryDB


class StudyStore:
    """Wraps the study-content SQLite tables with a clean save/get interface."""

    def __init__(self, db: HistoryDB | None = None) -> None:
        self._db = db or HistoryDB()
        self._owns_db = db is None

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------

    def save_summary(self, video_id: int, text: str, *, user_id: str | None = None) -> int:
        """Insert (or replace) a summary for *video_id*. Returns the new row id."""
        # Remove any existing summary for this video so there is only one.
        self._db._conn.execute(
            "DELETE FROM summaries WHERE video_id = ?", (video_id,)
        )
        cur = self._db._conn.execute(
            "INSERT INTO summaries (video_id, text, user_id) VALUES (?, ?, ?)",
            (video_id, text, user_id),
        )
        self._db._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_summary(self, video_id: int) -> dict | None:
        """Return {id, video_id, text, generated_at, user_id} or None."""
        row = self._db._conn.execute(
            "SELECT id, video_id, text, generated_at, user_id "
            "FROM summaries WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "video_id": row[1],
            "text": row[2],
            "generated_at": row[3],
            "user_id": row[4],
        }

    # ------------------------------------------------------------------
    # Q&A pairs
    # ------------------------------------------------------------------

    def save_qa_pairs(
        self,
        video_id: int,
        pairs: list[dict],
        *,
        user_id: str | None = None,
    ) -> None:
        """Replace all Q&A pairs for *video_id* with *pairs*.

        Each dict in *pairs* must have ``question`` and ``answer`` keys.
        The optional ``starred`` key (bool) flags teacher-emphasized items.
        """
        self._db._conn.execute(
            "DELETE FROM qa_pairs WHERE video_id = ?", (video_id,)
        )
        for sort_order, pair in enumerate(pairs):
            starred = int(bool(pair.get("starred", False)))
            self._db._conn.execute(
                "INSERT INTO qa_pairs "
                "(video_id, question, answer, sort_order, starred, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (video_id, pair["question"], pair["answer"], sort_order, starred, user_id),
            )
        self._db._conn.commit()

    def get_qa_pairs(self, video_id: int) -> list[dict]:
        """Return all Q&A pairs for *video_id* ordered by sort_order."""
        rows = self._db._conn.execute(
            "SELECT id, video_id, question, answer, sort_order, starred, user_id "
            "FROM qa_pairs WHERE video_id = ? ORDER BY sort_order",
            (video_id,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "video_id": r[1],
                "question": r[2],
                "answer": r[3],
                "sort_order": r[4],
                "starred": bool(r[5]),
                "user_id": r[6],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Flashcards
    # ------------------------------------------------------------------

    def save_flashcards(
        self,
        video_id: int,
        cards: list[dict],
        *,
        user_id: str | None = None,
    ) -> None:
        """Replace all flashcards for *video_id* with *cards*.

        Each dict in *cards* must have ``concept`` and ``definition`` keys.
        The optional ``starred`` key (bool) flags teacher-emphasized items.
        """
        self._db._conn.execute(
            "DELETE FROM flashcards WHERE video_id = ?", (video_id,)
        )
        for sort_order, card in enumerate(cards):
            starred = int(bool(card.get("starred", False)))
            self._db._conn.execute(
                "INSERT INTO flashcards "
                "(video_id, concept, definition, sort_order, starred, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (video_id, card["concept"], card["definition"], sort_order, starred, user_id),
            )
        self._db._conn.commit()

    def get_flashcards(self, video_id: int) -> list[dict]:
        """Return all flashcards for *video_id* ordered by sort_order."""
        rows = self._db._conn.execute(
            "SELECT id, video_id, concept, definition, sort_order, starred, user_id "
            "FROM flashcards WHERE video_id = ? ORDER BY sort_order",
            (video_id,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "video_id": r[1],
                "concept": r[2],
                "definition": r[3],
                "sort_order": r[4],
                "starred": bool(r[5]),
                "user_id": r[6],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Fill-in-the-blank
    # ------------------------------------------------------------------

    def save_fill_in_blank(
        self,
        video_id: int,
        items: list[dict],
        *,
        user_id: str | None = None,
    ) -> None:
        """Replace all fill-in-blank items for *video_id* with *items*.

        Each dict in *items* must have ``sentence`` and ``answer`` keys.
        The optional ``hint`` key (str) provides a short hint.
        The optional ``starred`` key (bool) flags teacher-emphasized items.
        """
        self._db._conn.execute(
            "DELETE FROM fill_in_blank WHERE video_id = ?", (video_id,)
        )
        for sort_order, item in enumerate(items):
            starred = int(bool(item.get("starred", False)))
            self._db._conn.execute(
                "INSERT INTO fill_in_blank "
                "(video_id, sentence, answer, hint, sort_order, starred, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    video_id,
                    item["sentence"],
                    item["answer"],
                    item.get("hint", ""),
                    sort_order,
                    starred,
                    user_id,
                ),
            )
        self._db._conn.commit()

    def get_fill_in_blank(self, video_id: int) -> list[dict]:
        """Return all fill-in-blank items for *video_id* ordered by sort_order."""
        rows = self._db._conn.execute(
            "SELECT id, sentence, answer, hint, sort_order, starred "
            "FROM fill_in_blank WHERE video_id = ? ORDER BY sort_order",
            (video_id,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "sentence": r[1],
                "answer": r[2],
                "hint": r[3],
                "sort_order": r[4],
                "starred": bool(r[5]),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # True/False statements
    # ------------------------------------------------------------------

    def save_true_false(
        self,
        video_id: int,
        items: list[dict],
        user_id: str | None = None,
    ) -> None:
        """Replace all true/false statements for *video_id* with *items*.

        Each dict in *items* must have ``statement`` and ``is_true`` keys.
        The optional ``explanation`` key (str) explains why it's true or false.
        The optional ``starred`` key (bool) flags teacher-emphasized items.
        """
        self._db._conn.execute(
            "DELETE FROM true_false_statements WHERE video_id = ?", (video_id,)
        )
        for sort_order, item in enumerate(items):
            starred = int(bool(item.get("starred", False)))
            is_true = int(bool(item.get("is_true", True)))
            self._db._conn.execute(
                "INSERT INTO true_false_statements "
                "(video_id, statement, is_true, explanation, sort_order, starred, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    video_id,
                    item["statement"],
                    is_true,
                    item.get("explanation", ""),
                    sort_order,
                    starred,
                    user_id,
                ),
            )
        self._db._conn.commit()

    def get_true_false(self, video_id: int) -> list[dict]:
        """Return all true/false statements for *video_id* ordered by sort_order."""
        rows = self._db._conn.execute(
            "SELECT id, video_id, statement, is_true, explanation, sort_order, starred "
            "FROM true_false_statements WHERE video_id = ? ORDER BY sort_order",
            (video_id,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "video_id": r[1],
                "statement": r[2],
                "is_true": bool(r[3]),
                "explanation": r[4],
                "sort_order": r[5],
                "starred": bool(r[6]),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Error Detection items
    # ------------------------------------------------------------------

    def save_error_detection(
        self,
        video_id: int,
        items: list[dict],
        user_id: str | None = None,
    ) -> None:
        """Replace all error-detection items for *video_id* with *items*.

        Each dict in *items* must have ``statement``, ``error``, and ``correction`` keys.
        The optional ``explanation`` key (str) explains the correct version.
        The optional ``starred`` key (bool) flags teacher-emphasized items.
        """
        self._db._conn.execute(
            "DELETE FROM error_detection_items WHERE video_id = ?", (video_id,)
        )
        for sort_order, item in enumerate(items):
            starred = int(bool(item.get("starred", False)))
            self._db._conn.execute(
                "INSERT INTO error_detection_items "
                "(video_id, statement, error, correction, explanation, sort_order, starred, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    video_id,
                    item["statement"],
                    item["error"],
                    item["correction"],
                    item.get("explanation", ""),
                    sort_order,
                    starred,
                    user_id,
                ),
            )
        self._db._conn.commit()

    def get_error_detection(self, video_id: int) -> list[dict]:
        """Return all error-detection items for *video_id* ordered by sort_order."""
        rows = self._db._conn.execute(
            "SELECT id, statement, error, correction, explanation, sort_order, starred "
            "FROM error_detection_items WHERE video_id = ? ORDER BY sort_order",
            (video_id,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "statement": r[1],
                "error": r[2],
                "correction": r[3],
                "explanation": r[4],
                "sort_order": r[5],
                "starred": bool(r[6]),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Action items
    # ------------------------------------------------------------------

    def save_action_items(
        self,
        video_id: int,
        items: list[dict],
        *,
        user_id: str | None = None,
    ) -> None:
        """Replace all action items for *video_id* with *items*.

        Each dict must have ``text`` and ``urgency`` keys; ``extracted_date`` is optional.
        Valid urgency values: ``'high'``, ``'medium'``, ``'low'``.
        """
        self._db._conn.execute(
            "DELETE FROM action_items WHERE video_id = ?", (video_id,)
        )
        for item in items:
            self._db._conn.execute(
                "INSERT INTO action_items "
                "(video_id, text, urgency, extracted_date, user_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    video_id,
                    item["text"],
                    item["urgency"],
                    item.get("extracted_date"),
                    user_id,
                ),
            )
        self._db._conn.commit()

    def get_action_items(self, video_id: int) -> list[dict]:
        """Return all action items for *video_id* ordered by creation."""
        rows = self._db._conn.execute(
            "SELECT id, video_id, text, urgency, extracted_date, dismissed, user_id, created_at "
            "FROM action_items WHERE video_id = ? ORDER BY id",
            (video_id,),
        ).fetchall()
        return [_action_item_row(r) for r in rows]

    def get_all_alerts(self, *, dismissed: bool = False) -> list[dict]:
        """Return all action items across every video.

        By default only undismissed items are returned. Pass ``dismissed=True``
        to include dismissed ones as well.
        """
        if dismissed:
            rows = self._db._conn.execute(
                "SELECT id, video_id, text, urgency, extracted_date, dismissed, user_id, created_at "
                "FROM action_items ORDER BY id"
            ).fetchall()
        else:
            rows = self._db._conn.execute(
                "SELECT id, video_id, text, urgency, extracted_date, dismissed, user_id, created_at "
                "FROM action_items WHERE dismissed = 0 ORDER BY id"
            ).fetchall()
        return [_action_item_row(r) for r in rows]

    def dismiss_action_item(self, item_id: int) -> None:
        """Mark a single action item as dismissed."""
        self._db._conn.execute(
            "UPDATE action_items SET dismissed = 1 WHERE id = ?", (item_id,)
        )
        self._db._conn.commit()

    # ------------------------------------------------------------------
    # Card reviews (SM-2 spaced repetition)
    # ------------------------------------------------------------------

    def get_or_create_card_review(
        self, card_id: str, card_type: str, video_id: int, user_id: str | None = None
    ) -> dict:
        """Get existing card review or create new one if doesn't exist.

        Returns a dict with keys:
        {card_id, card_type, video_id, ease_factor, interval, repetitions, next_review, last_reviewed, user_id}
        """
        # Try to fetch existing
        row = self._db._conn.execute(
            "SELECT id, card_id, card_type, video_id, ease_factor, interval, repetitions, next_review, last_reviewed, user_id "
            "FROM card_reviews WHERE card_id = ? AND card_type = ? AND video_id = ? AND COALESCE(user_id, '') = COALESCE(?, '')",
            (card_id, card_type, video_id, user_id),
        ).fetchone()

        if row is not None:
            return {
                "id": row[0],
                "card_id": row[1],
                "card_type": row[2],
                "video_id": row[3],
                "ease_factor": row[4],
                "interval": row[5],
                "repetitions": row[6],
                "next_review": row[7],
                "last_reviewed": row[8],
                "user_id": row[9],
            }

        # Create new review with SM-2 defaults
        today_str = date.today().isoformat()
        self._db._conn.execute(
            "INSERT INTO card_reviews "
            "(card_id, card_type, video_id, ease_factor, interval, repetitions, next_review, user_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (card_id, card_type, video_id, 2.5, 1, 0, today_str, user_id),
        )
        self._db._conn.commit()

        # Return the newly created row
        row = self._db._conn.execute(
            "SELECT id, card_id, card_type, video_id, ease_factor, interval, repetitions, next_review, last_reviewed, user_id "
            "FROM card_reviews WHERE card_id = ? AND card_type = ? AND video_id = ? AND COALESCE(user_id, '') = COALESCE(?, '')",
            (card_id, card_type, video_id, user_id),
        ).fetchone()
        return {
            "id": row[0],
            "card_id": row[1],
            "card_type": row[2],
            "video_id": row[3],
            "ease_factor": row[4],
            "interval": row[5],
            "repetitions": row[6],
            "next_review": row[7],
            "last_reviewed": row[8],
            "user_id": row[9],
        }

    def update_card_review(
        self, card_id: str, card_type: str, video_id: int, quality: int, user_id: str | None = None
    ) -> dict:
        """Apply SM-2 algorithm after a review (quality 1-5).

        Computes new EF, interval, repetitions, and next_review.
        Returns the updated row as dict.
        """
        review = self.get_or_create_card_review(card_id, card_type, video_id, user_id)

        # Log this review event for weekly failure tracking (SEB-87 Boss Battle)
        self._db.log_card_review_event(
            card_id=card_id,
            card_type=card_type,
            video_id=video_id,
            quality=quality,
            user_id=user_id,
        )

        ef = review["ease_factor"]
        interval = review["interval"]
        repetitions = review["repetitions"]

        # SM-2 formula: new_EF = max(1.3, EF + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
        new_ef = max(1.3, ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))

        if quality < 3:
            # Recall failure: reset
            new_repetitions = 1
            new_interval = 1
        else:
            # Recall success
            new_repetitions = repetitions + 1
            if new_repetitions == 1:
                new_interval = 1
            elif new_repetitions == 2:
                new_interval = 3
            else:
                new_interval = int(round(interval * new_ef))

        # Calculate next review date
        today = date.today()
        next_review_date = today + timedelta(days=new_interval)
        next_review_str = next_review_date.isoformat()
        today_str = today.isoformat()

        # Update the record
        self._db._conn.execute(
            "UPDATE card_reviews "
            "SET ease_factor = ?, interval = ?, repetitions = ?, next_review = ?, last_reviewed = ?, updated_at = datetime('now') "
            "WHERE card_id = ? AND card_type = ? AND video_id = ? AND COALESCE(user_id, '') = COALESCE(?, '')",
            (new_ef, new_interval, new_repetitions, next_review_str, today_str, card_id, card_type, video_id, user_id),
        )
        self._db._conn.commit()

        # Fetch and return updated row
        row = self._db._conn.execute(
            "SELECT id, card_id, card_type, video_id, ease_factor, interval, repetitions, next_review, last_reviewed, user_id "
            "FROM card_reviews WHERE card_id = ? AND card_type = ? AND video_id = ? AND COALESCE(user_id, '') = COALESCE(?, '')",
            (card_id, card_type, video_id, user_id),
        ).fetchone()
        return {
            "id": row[0],
            "card_id": row[1],
            "card_type": row[2],
            "video_id": row[3],
            "ease_factor": row[4],
            "interval": row[5],
            "repetitions": row[6],
            "next_review": row[7],
            "last_reviewed": row[8],
            "user_id": row[9],
        }

    def get_cards_due_today(self, video_id: int, user_id: str | None = None) -> set[str]:
        """Return set of card_ids that are due for review today or earlier.

        Used for optional filtering in the frontend to show only due cards.
        """
        today_str = date.today().isoformat()
        rows = self._db._conn.execute(
            "SELECT card_id FROM card_reviews "
            "WHERE video_id = ? AND next_review <= ? AND COALESCE(user_id, '') = COALESCE(?, '')",
            (video_id, today_str, user_id),
        ).fetchall()
        return {row[0] for row in rows}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        if self._owns_db:
            self._db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _action_item_row(r: tuple) -> dict:
    return {
        "id": r[0],
        "video_id": r[1],
        "text": r[2],
        "urgency": r[3],
        "extracted_date": r[4],
        "dismissed": bool(r[5]),
        "user_id": r[6],
        "created_at": r[7],
    }
