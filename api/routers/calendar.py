from typing import List, Optional
from fastapi import APIRouter, Query, Depends, Request
import logging

from models.calendar import CalendarEvent
from core.database_service import get_all_events_from_db

logger = logging.getLogger(__name__)

from core.security import verify_client_token, verify_app_check_token
from core.rate_limit import limiter

router = APIRouter(
    prefix="/calendar",
    tags=["calendar"],
    dependencies=[Depends(verify_client_token), Depends(verify_app_check_token)],
)

@router.get("", response_model=List[CalendarEvent])
@limiter.limit("60/minute")
async def get_calendar(
    request: Request,
    year: Optional[int] = Query(None, description="Filter events by year"),
    categories: Optional[List[str]] = Query(None, description="Filter by a list of categories (e.g., WRC, F1). If not provided, all are returned.")
):
    """
    Get calendar events for various championships.
    All data is read directly from the historic database, which is updated daily and on startup.
    """
    try:
        all_events = await get_all_events_from_db()
    except Exception as e:
        logger.error(f"Failed to fetch events from DB: {e}")
        all_events = []

    # Sort chronological
    all_events.sort(key=lambda x: x.start_date)

    filtered_events = all_events

    if categories:
        lower_categories = [cat.lower() for cat in categories]
        filtered_events = [event for event in filtered_events if event.category.lower() in lower_categories]

    if year is not None:
        filtered_events = [event for event in filtered_events if event.start_date.year == year]
    
    return filtered_events
