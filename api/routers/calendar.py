from typing import List, Optional
from fastapi import APIRouter, Query
import logging

from models.calendar import CalendarEvent
from core.database_service import get_all_events_from_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/calendar",
    tags=["calendar"],
)

@router.get("", response_model=List[CalendarEvent])
async def get_calendar(
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
