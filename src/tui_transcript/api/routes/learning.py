"""Routes for card-level operations (spaced repetition, rating)."""

from __future__ import annotations

from fastapi import APIRouter

from tui_transcript.api.schemas import CardReviewResponse, RateCardRequest
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
