"""Routes for card-level operations (spaced repetition, rating, boss battle)."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter

from tui_transcript.api.schemas import (
    BossBattleResponse,
    CardReviewResponse,
    RateCardRequest,
    WeeklyFailingCard,
)
from tui_transcript.services.history import HistoryDB
from tui_transcript.services.study_store import StudyStore

router = APIRouter(prefix="/classes", tags=["learning"])


@router.post("/{video_id}/cards/{card_id}/rate", response_model=CardReviewResponse)
def rate_card(video_id: int, card_id: str, body: RateCardRequest) -> CardReviewResponse:
    """Rate a card (1-5) and apply SM-2 algorithm to compute next review date.

    Expects body: {card_type: str, quality: int (1-5)}
    Returns: {card_id, next_review, ease_factor, interval, repetitions}
    """
    db = HistoryDB()
    try:
        store = StudyStore(db)
        result = store.update_card_review(
            card_id=card_id,
            card_type=body.card_type,
            video_id=video_id,
            quality=body.quality,
        )
        return CardReviewResponse(
            card_id=result["card_id"],
            next_review=result["next_review"],
            ease_factor=result["ease_factor"],
            interval=result["interval"],
            repetitions=result["repetitions"],
        )
    finally:
        db.close()


@router.get("/{video_id}/boss-battle", response_model=BossBattleResponse)
def get_boss_battle(video_id: int) -> BossBattleResponse:
    """Return the top-20 cards the student failed this week for *video_id*.

    Week resets every Monday. Failures are reviews with quality < 3.
    """
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    db = HistoryDB()
    try:
        rows = db.get_weekly_failures(video_id, limit=20)
        return BossBattleResponse(
            video_id=video_id,
            week_start=monday.isoformat(),
            cards=[WeeklyFailingCard(**r) for r in rows],
        )
    finally:
        db.close()


@router.post("/{video_id}/boss-battle/complete", status_code=204)
def complete_boss_battle(video_id: int) -> None:
    """Record a boss-battle completion in activity_log (unlocks the badge)."""
    db = HistoryDB()
    try:
        today = date.today().isoformat()
        db._conn.execute(
            """
            INSERT INTO activity_log (log_date, activity_type, items_done, items_correct)
            VALUES (?, 'boss_battle', 1, 1)
            ON CONFLICT(log_date, activity_type, COALESCE(user_id, '')) DO UPDATE SET
                items_done    = items_done    + 1,
                items_correct = items_correct + 1
            """,
            (today,),
        )
        db._conn.commit()
    finally:
        db.close()
