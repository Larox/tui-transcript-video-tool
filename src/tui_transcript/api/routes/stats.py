"""API routes for study stats, streaks and daily goals (SEB-81, SEB-90)."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter

from tui_transcript.api.schemas import (
    DailySessionEntry,
    LogSessionRequest,
    StatsSummaryResponse,
)
from tui_transcript.services.history import HistoryDB

router = APIRouter(prefix="/stats", tags=["stats"])

DAILY_GOAL = 10  # cards per day


def _db() -> HistoryDB:
    return HistoryDB()


def _today() -> str:
    return date.today().isoformat()


def _compute_streak(session_dates: set[str]) -> tuple[int, int]:
    """Return (current_streak, longest_streak) from a set of YYYY-MM-DD strings."""
    if not session_dates:
        return 0, 0

    today = date.today()
    # Current streak — walk backwards from today
    current = 0
    cursor = today
    while cursor.isoformat() in session_dates:
        current += 1
        cursor -= timedelta(days=1)

    # If today has no session yet, try counting from yesterday
    if current == 0:
        cursor = today - timedelta(days=1)
        while cursor.isoformat() in session_dates:
            current += 1
            cursor -= timedelta(days=1)

    # Longest streak — walk through sorted dates
    sorted_dates = sorted(date.fromisoformat(d) for d in session_dates)
    longest = 1
    run = 1
    for i in range(1, len(sorted_dates)):
        if sorted_dates[i] - sorted_dates[i - 1] == timedelta(days=1):
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    return current, longest


@router.post("/session", status_code=204)
def log_session(body: LogSessionRequest) -> None:
    """Log (or update) a study session for today.

    One row per calendar day — upserts by adding to existing counts.
    """
    db = _db()
    try:
        today = _today()
        conn = db._conn
        # Try to insert; on conflict (same date + null user_id) add to existing counts
        conn.execute(
            """
            INSERT INTO study_sessions (session_date, cards_reviewed, quizzes_correct, quizzes_total)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_date, COALESCE(user_id, '')) DO UPDATE SET
                cards_reviewed  = cards_reviewed  + excluded.cards_reviewed,
                quizzes_correct = quizzes_correct + excluded.quizzes_correct,
                quizzes_total   = quizzes_total   + excluded.quizzes_total
            """,
            (today, body.cards_reviewed, body.quizzes_correct, body.quizzes_total),
        )
        conn.commit()
    finally:
        db.close()


@router.get("/summary", response_model=StatsSummaryResponse)
def get_summary() -> StatsSummaryResponse:
    """Return full stats summary for the dashboard and stats page."""
    db = _db()
    try:
        conn = db._conn

        # All sessions
        rows = conn.execute(
            "SELECT session_date, cards_reviewed, quizzes_correct, quizzes_total "
            "FROM study_sessions ORDER BY session_date"
        ).fetchall()

        all_sessions = [
            {"date": r[0], "cards_reviewed": r[1], "quizzes_correct": r[2], "quizzes_total": r[3]}
            for r in rows
        ]

        # Totals
        total_sessions = len(all_sessions)
        total_cards = sum(s["cards_reviewed"] for s in all_sessions)
        total_correct = sum(s["quizzes_correct"] for s in all_sessions)
        total_total = sum(s["quizzes_total"] for s in all_sessions)

        # Streaks
        session_dates = {s["date"] for s in all_sessions}
        current_streak, longest_streak = _compute_streak(session_dates)

        # Last 30 days
        today = date.today()
        cutoff = (today - timedelta(days=29)).isoformat()
        last_30 = [
            DailySessionEntry(
                date=s["date"],
                cards_reviewed=s["cards_reviewed"],
                quizzes_correct=s["quizzes_correct"],
                quizzes_total=s["quizzes_total"],
            )
            for s in all_sessions
            if s["date"] >= cutoff
        ]

        # Today's cards
        today_str = today.isoformat()
        today_row = next((s for s in all_sessions if s["date"] == today_str), None)
        today_cards = today_row["cards_reviewed"] if today_row else 0

        return StatsSummaryResponse(
            current_streak=current_streak,
            longest_streak=longest_streak,
            total_sessions=total_sessions,
            total_cards_reviewed=total_cards,
            total_quizzes_correct=total_correct,
            total_quizzes_total=total_total,
            sessions_last_30_days=last_30,
            daily_goal=DAILY_GOAL,
            today_cards=today_cards,
        )
    finally:
        db.close()
