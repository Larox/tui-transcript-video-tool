"""API routes for the dashboard (cross-course alerts)."""

from __future__ import annotations

from fastapi import APIRouter

from tui_transcript.api.schemas import AlertEntry, AlertsResponse
from tui_transcript.services.study_store import StudyStore

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_URGENCY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _store() -> StudyStore:
    return StudyStore()


@router.get("/alerts", response_model=AlertsResponse)
def get_alerts() -> AlertsResponse:
    """Return all undismissed action items across all courses, sorted by urgency then date."""
    store = _store()
    try:
        items = store.get_all_alerts(dismissed=False)
    finally:
        store.close()

    items.sort(
        key=lambda item: (
            _URGENCY_ORDER.get(item["urgency"], 99),
            item["extracted_date"] or "",
        )
    )

    return AlertsResponse(
        alerts=[
            AlertEntry(
                id=item["id"],
                video_id=item["video_id"],
                text=item["text"],
                urgency=item["urgency"],
                extracted_date=item["extracted_date"],
                dismissed=item["dismissed"],
                created_at=item["created_at"],
            )
            for item in items
        ]
    )
