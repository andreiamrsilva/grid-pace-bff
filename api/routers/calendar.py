from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
import httpx
import time
import asyncio
from datetime import datetime

import sys
import os

# Adds the openWrc/src directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "openWrc", "src")))

from openwrc.clients.wrc_api_client import WrcApiClient
from models.calendar import CalendarEvent
from api.utils import get_logo_path
from api.f1_client import get_f1_calendar_events
import logging
import traceback

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/calendar",
    tags=["calendar"],
)

# In-memory cache
cache = {
    "data": [],
    "timestamp": 0,
    "is_updating": False
}
CACHE_DURATION = 604800  # 1 week

async def fetch_wrc_events() -> List[CalendarEvent]:
    """Fetches all WRC calendar events."""
    logger.info("Fetching WRC events...")
    wrc_events = []
    try:
        async with WrcApiClient() as client:
            all_seasons = await client.get_seasons()
            seasons = [s for s in all_seasons if "world rally championship" in s.name.lower()]
            
            for season in seasons:
                season_detail = await client.get_season_detail(season.season_id)
                if not season_detail or not season_detail.season_rounds:
                    continue
                
                for round_info in season_detail.season_rounds:
                    if not round_info.event:
                        continue
                    
                    current_leader = None
                    current_leader_logo_path = None
                    try:
                        event_metadata = await client.get_event_metadata(round_info.event.event_id)
                        if event_metadata and event_metadata.rallies:
                            rally_id = event_metadata.rallies[0].rally_id
                            results = await client.get_rally_results(round_info.event.event_id, rally_id)
                            
                            if results:
                                leader_result = next((r for r in results if r.position == 1), None)
                                
                                if leader_result:
                                    entries = await client.get_rally_entries(round_info.event.event_id, rally_id)
                                    leader_entry = next((e for e in entries if e.entry_id == leader_result.entry_id), None)
                                    if leader_entry:
                                        current_leader = leader_entry.driver.full_name
                                        if hasattr(leader_entry, 'manufacturer') and leader_entry.manufacturer:
                                            current_leader_logo_path = get_logo_path(leader_entry.manufacturer.name)

                    except Exception as e:
                        logger.warning(f"Could not fetch WRC leader for event {round_info.event.event_id}: {e}")

                    wrc_events.append(
                        CalendarEvent(
                            id=round_info.event.event_id,
                            name=round_info.event.name,
                            category="WRC",
                            country=round_info.event.country.name if hasattr(round_info.event, 'country') else "Unknown",
                            country_image_url=f"https://flagcdn.com/w320/{round_info.event.country.iso2.lower()}.png" if hasattr(round_info.event, 'country') and hasattr(round_info.event.country, 'iso2') else None,
                            start_date=round_info.event.start_date,
                            finish_date=round_info.event.finish_date,
                            current_leader=current_leader,
                            current_leader_logo_path=current_leader_logo_path,
                        )
                    )
    except Exception as e:
        logger.error(f"Error fetching WRC events: {e}")
    
    logger.info(f"Fetched {len(wrc_events)} WRC events.")
    return wrc_events

async def update_calendar_cache():
    """Fetches calendar data from all sources (WRC, F1) and updates the cache."""
    global cache
    
    if cache["is_updating"]:
        return
        
    cache["is_updating"] = True
    logger.info("Starting combined calendar cache update.")
    
    current_year = datetime.now().year
    
    # Fetch data from all sources in parallel
    wrc_task = fetch_wrc_events()
    f1_task = get_f1_calendar_events(current_year)
    
    results = await asyncio.gather(wrc_task, f1_task, return_exceptions=True)
    
    combined_events = []
    for result in results:
        if isinstance(result, list):
            combined_events.extend(result)
        elif isinstance(result, Exception):
            logger.error(f"An error occurred during cache update: {result}")

    # Sort all events by start date
    combined_events.sort(key=lambda x: x.start_date)
    
    # Update cache atomically
    cache["data"] = combined_events
    cache["timestamp"] = time.time()
    cache["is_updating"] = False
    logger.info(f"Combined calendar cache updated with {len(combined_events)} events.")

async def periodic_cache_updater():
    """Runs continuously in the background to update the cache."""
    while True:
        await update_calendar_cache()
        await asyncio.sleep(CACHE_DURATION)

@router.get("", response_model=List[CalendarEvent])
async def get_calendar(
    year: Optional[int] = Query(None, description="Filter events by year"),
    categories: Optional[List[str]] = Query(None, description="Filter by a list of categories (e.g., WRC, F1). If not provided, all are returned.")
):
    """
    Get calendar events for various championships.
    """
    global cache
    
    while cache["is_updating"] and not cache["data"]:
        await asyncio.sleep(0.5)
    
    if not cache["data"] and not cache["is_updating"]:
        await update_calendar_cache()

    filtered_events = cache["data"]
    
    # If no categories are provided, we don't filter (return all)
    if categories:
        lower_categories = [cat.lower() for cat in categories]
        filtered_events = [event for event in filtered_events if event.category.lower() in lower_categories]

    if year is not None:
        filtered_events = [event for event in filtered_events if event.start_date.year == year]
    
    return filtered_events
