"""Service for accessing generated study content (summaries, Q&A, flashcards, action items)."""

from __future__ import annotations

from tui_transcript.services.history import DB_PATH, HistoryDB

from pathlib import Path


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
