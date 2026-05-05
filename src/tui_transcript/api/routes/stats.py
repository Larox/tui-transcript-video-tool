"""API routes for study stats, streaks and daily goals (SEB-81, SEB-90)."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter

from tui_transcript.api.schemas import (
    DailySessionEntry,
    LogActivityRequest,
    StatsSummaryResponse,
)
from tui_transcript.services.history import HistoryDB

router = APIRouter(prefix="/stats", tags=["stats"])

DAILY_GOAL = 10  # items per day


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


@router.post("/activity", status_code=204)
def log_activity(body: LogActivityRequest) -> None:
    """Log (or update) an activity entry for today.

    One row per (calendar day, activity_type) — upserts by accumulating on conflict.
    """
    db = _db()
    try:
        today = _today()
        conn = db._conn
        conn.execute(
            """
            INSERT INTO activity_log (log_date, activity_type, items_done, items_correct)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(log_date, activity_type, COALESCE(user_id, '')) DO UPDATE SET
                items_done    = items_done    + excluded.items_done,
                items_correct = items_correct + excluded.items_correct
            """,
            (today, body.activity_type, body.items_done, body.items_correct),
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

        # Total sessions = COUNT(DISTINCT log_date)
        total_sessions_row = conn.execute(
            "SELECT COUNT(DISTINCT log_date) FROM activity_log"
        ).fetchone()
        total_sessions = total_sessions_row[0] if total_sessions_row else 0

        # Totals across all activity types
        totals_row = conn.execute(
            "SELECT COALESCE(SUM(items_done), 0), COALESCE(SUM(items_correct), 0) "
            "FROM activity_log"
        ).fetchone()
        total_items_done = totals_row[0] if totals_row else 0
        total_items_correct = totals_row[1] if totals_row else 0

        # Distinct log_dates for streak calculation
        date_rows = conn.execute(
            "SELECT DISTINCT log_date FROM activity_log ORDER BY log_date"
        ).fetchall()
        session_dates = {r[0] for r in date_rows}
        current_streak, longest_streak = _compute_streak(session_dates)

        # Last 30 days: GROUP BY log_date, SUM items_done and items_correct
        today = date.today()
        cutoff = (today - timedelta(days=29)).isoformat()
        last_30_rows = conn.execute(
            """
            SELECT log_date, SUM(items_done), SUM(items_correct)
            FROM activity_log
            WHERE log_date >= ?
            GROUP BY log_date
            ORDER BY log_date
            """,
            (cutoff,),
        ).fetchall()
        last_30 = [
            DailySessionEntry(
                date=r[0],
                items_done=r[1],
                items_correct=r[2],
            )
            for r in last_30_rows
        ]

        # Today's items
        today_str = today.isoformat()
        today_row = conn.execute(
            "SELECT COALESCE(SUM(items_done), 0) FROM activity_log WHERE log_date = ?",
            (today_str,),
        ).fetchone()
        today_items = today_row[0] if today_row else 0

        return StatsSummaryResponse(
            current_streak=current_streak,
            longest_streak=longest_streak,
            total_sessions=total_sessions,
            total_items_done=total_items_done,
            total_items_correct=total_items_correct,
            sessions_last_30_days=last_30,
            daily_goal=DAILY_GOAL,
            today_items=today_items,
        )
    finally:
        db.close()
