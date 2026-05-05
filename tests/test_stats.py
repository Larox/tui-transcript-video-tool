"""Tests for the activity_log-based stats system."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tui_transcript.services.history import HistoryDB
from tui_transcript.api.routes.stats import _compute_streak


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> HistoryDB:
    """Fresh SQLite DB in a temp dir."""
    db = HistoryDB(tmp_path / "test_stats.db")
    yield db
    db.close()


@pytest.fixture()
def client(tmp_path: Path):
    """TestClient wired to a temp DB via patched DB_PATH."""
    test_db_path = tmp_path / "test_stats.db"

    import tui_transcript.services.history as history_mod
    import tui_transcript.api.routes.stats as stats_mod

    # Patch _db() to always return a connection to our temp DB
    def _fake_db():
        return HistoryDB(test_db_path)

    with patch.object(stats_mod, "_db", _fake_db):
        from tui_transcript.api.main import app
        with TestClient(app) as c:
            yield c


# ---------------------------------------------------------------------------
# _compute_streak
# ---------------------------------------------------------------------------


def test_compute_streak_empty():
    current, longest = _compute_streak(set())
    assert current == 0
    assert longest == 0


def test_compute_streak_single_today():
    today = date.today().isoformat()
    current, longest = _compute_streak({today})
    assert current == 1
    assert longest == 1


def test_compute_streak_consecutive_including_today():
    today = date.today()
    dates = {(today - timedelta(days=i)).isoformat() for i in range(3)}
    current, longest = _compute_streak(dates)
    assert current == 3
    assert longest == 3


def test_compute_streak_gap_resets_current():
    today = date.today()
    # yesterday and 3+4 days ago — gap of 1 day breaks the current streak from today
    dates = {
        (today - timedelta(days=1)).isoformat(),
        (today - timedelta(days=3)).isoformat(),
        (today - timedelta(days=4)).isoformat(),
    }
    current, longest = _compute_streak(dates)
    assert current == 1      # only yesterday
    assert longest == 2      # days 3 and 4 ago


# ---------------------------------------------------------------------------
# activity_log upsert (via raw DB)
# ---------------------------------------------------------------------------


def test_log_activity_inserts_new_row(db):
    today = date.today().isoformat()
    conn = db._conn
    conn.execute(
        "INSERT INTO activity_log (log_date, activity_type, items_done, items_correct) "
        "VALUES (?, 'flashcard', 5, 5)",
        (today,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT items_done FROM activity_log WHERE log_date = ? AND activity_type = 'flashcard'",
        (today,),
    ).fetchone()
    assert row[0] == 5


def test_log_activity_accumulates_on_conflict(db):
    today = date.today().isoformat()
    conn = db._conn

    for done, correct in [(10, 7), (5, 4)]:
        conn.execute(
            """
            INSERT INTO activity_log (log_date, activity_type, items_done, items_correct)
            VALUES (?, 'quiz', ?, ?)
            ON CONFLICT(log_date, activity_type, COALESCE(user_id, '')) DO UPDATE SET
                items_done    = items_done    + excluded.items_done,
                items_correct = items_correct + excluded.items_correct
            """,
            (today, done, correct),
        )
    conn.commit()

    row = conn.execute(
        "SELECT items_done, items_correct FROM activity_log "
        "WHERE log_date = ? AND activity_type = 'quiz'",
        (today,),
    ).fetchone()
    assert row[0] == 15   # 10 + 5
    assert row[1] == 11   # 7 + 4


def test_different_activity_types_same_day(db):
    """Different activity types on same day create separate rows."""
    today = date.today().isoformat()
    conn = db._conn
    for activity_type, done, correct in [('flashcard', 5, 5), ('quiz', 10, 7), ('fill_in_blank', 3, 2)]:
        conn.execute(
            "INSERT INTO activity_log (log_date, activity_type, items_done, items_correct) "
            "VALUES (?, ?, ?, ?)",
            (today, activity_type, done, correct),
        )
    conn.commit()

    rows = conn.execute(
        "SELECT activity_type, items_done, items_correct FROM activity_log "
        "WHERE log_date = ? ORDER BY activity_type",
        (today,),
    ).fetchall()
    assert len(rows) == 3
    by_type = {r[0]: (r[1], r[2]) for r in rows}
    assert by_type['flashcard'] == (5, 5)
    assert by_type['quiz'] == (10, 7)
    assert by_type['fill_in_blank'] == (3, 2)


# ---------------------------------------------------------------------------
# get_summary aggregation (raw DB)
# ---------------------------------------------------------------------------


def test_get_summary_totals_aggregate_across_types(db):
    """total_items_done / total_items_correct sum across all activity types."""
    today = date.today().isoformat()
    conn = db._conn
    conn.executemany(
        "INSERT INTO activity_log (log_date, activity_type, items_done, items_correct) VALUES (?, ?, ?, ?)",
        [
            (today, 'flashcard', 5, 5),
            (today, 'quiz', 10, 7),
            (today, 'fill_in_blank', 3, 2),
        ],
    )
    conn.commit()

    total_done = conn.execute("SELECT SUM(items_done) FROM activity_log").fetchone()[0]
    total_correct = conn.execute("SELECT SUM(items_correct) FROM activity_log").fetchone()[0]
    assert total_done == 18    # 5 + 10 + 3
    assert total_correct == 14  # 5 + 7 + 2


def test_get_summary_total_sessions_counts_distinct_days(db):
    """total_sessions = COUNT(DISTINCT log_date)."""
    conn = db._conn
    today = date.today()
    for offset, atype in [(0, 'flashcard'), (0, 'quiz'), (1, 'flashcard'), (2, 'quiz')]:
        day = (today - timedelta(days=offset)).isoformat()
        conn.execute(
            "INSERT INTO activity_log (log_date, activity_type, items_done, items_correct) VALUES (?, ?, 5, 5)",
            (day, atype),
        )
    conn.commit()

    distinct_days = conn.execute("SELECT COUNT(DISTINCT log_date) FROM activity_log").fetchone()[0]
    assert distinct_days == 3   # today, yesterday, 2 days ago


def test_daily_session_entry_aggregates_across_types(db):
    """DailySessionEntry groups by log_date and sums across activity types."""
    today = date.today().isoformat()
    conn = db._conn
    conn.executemany(
        "INSERT INTO activity_log (log_date, activity_type, items_done, items_correct) VALUES (?, ?, ?, ?)",
        [
            (today, 'flashcard', 4, 4),
            (today, 'quiz', 6, 5),
        ],
    )
    conn.commit()

    row = conn.execute(
        "SELECT SUM(items_done), SUM(items_correct) FROM activity_log WHERE log_date = ?",
        (today,),
    ).fetchone()
    assert row[0] == 10   # 4 + 6
    assert row[1] == 9    # 4 + 5


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def test_post_activity_returns_204(client):
    resp = client.post(
        '/api/stats/activity',
        json={'activity_type': 'flashcard', 'items_done': 5, 'items_correct': 5},
    )
    assert resp.status_code == 204


def test_post_activity_accumulates(client):
    client.post(
        '/api/stats/activity',
        json={'activity_type': 'quiz', 'items_done': 10, 'items_correct': 8},
    )
    client.post(
        '/api/stats/activity',
        json={'activity_type': 'quiz', 'items_done': 5, 'items_correct': 3},
    )
    summary = client.get('/api/stats/summary').json()
    assert summary['total_items_done'] == 15
    assert summary['total_items_correct'] == 11


def test_get_summary_empty_db(client):
    resp = client.get('/api/stats/summary')
    assert resp.status_code == 200
    data = resp.json()
    assert data['current_streak'] == 0
    assert data['longest_streak'] == 0
    assert data['total_sessions'] == 0
    assert data['total_items_done'] == 0
    assert data['total_items_correct'] == 0
    assert data['sessions_last_30_days'] == []
    assert data['today_items'] == 0


def test_get_summary_today_items(client):
    client.post(
        '/api/stats/activity',
        json={'activity_type': 'flashcard', 'items_done': 7, 'items_correct': 7},
    )
    client.post(
        '/api/stats/activity',
        json={'activity_type': 'quiz', 'items_done': 3, 'items_correct': 2},
    )
    summary = client.get('/api/stats/summary').json()
    assert summary['today_items'] == 10   # 7 + 3


def test_get_summary_streak(client):
    client.post(
        '/api/stats/activity',
        json={'activity_type': 'flashcard', 'items_done': 5, 'items_correct': 5},
    )
    summary = client.get('/api/stats/summary').json()
    assert summary['current_streak'] == 1


def test_old_session_endpoint_gone(client):
    """The old /stats/session endpoint no longer exists."""
    resp = client.post(
        '/api/stats/session',
        json={'cards_reviewed': 5, 'quizzes_correct': 3, 'quizzes_total': 5},
    )
    assert resp.status_code in (404, 405)
