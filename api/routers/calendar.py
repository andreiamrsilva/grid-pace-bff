from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
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
from api.database_service import get_historic_events_from_db
import logging
import traceback

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/calendar",
    tags=["calendar"],
)

# --- Cache Structure ---
# We now use the database for historic events.
# This cache only holds events for the current and next year.
cache = {"data": [], "timestamp": 0, "is_updating": False}
CACHE_DURATION = 300  # 5 minutes

# --- Data Fetching Functions ---

async def fetch_wrc_events_for_years(years: List[int]) -> List[CalendarEvent]:
    """Fetches WRC events for a specific list of years, including leader details."""
    logger.info(f"Fetching WRC events for years: {years}...")
    wrc_events = []
    try:
        async with WrcApiClient() as client:
            all_seasons = await client.get_seasons()
            seasons = [s for s in all_seasons if s.year in years and "world rally championship" in s.name.lower()]
            
            for season in seasons:
                season_detail = await client.get_season_detail(season.season_id)
                if not season_detail or not season_detail.season_rounds:
                    continue
                
                for round_info in season_detail.season_rounds:
                    if not round_info.event:
                        continue
                    
                    current_leader = None
                    current_leader_logo_path = None
                    
                    # Try to fetch leader details if the event has started
                    if round_info.event.start_date <= datetime.now().date():
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
                        except httpx.HTTPStatusError as e:
                            if e.response.status_code != 404:
                                logger.warning(f"HTTP error fetching WRC leader for event {round_info.event.event_id}: {e}")
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
    return wrc_events

async def update_recent_cache():
    """Fetches calendar data for recent years (current and next) and updates the cache."""
    global cache
    if cache["is_updating"]:
        return
        
    cache["is_updating"] = True
    logger.info("Starting recent calendar cache update.")
    
    current_year = datetime.now().year
    recent_years = [current_year, current_year + 1]
    
    wrc_task = fetch_wrc_events_for_years(recent_years)
    f1_tasks = [get_f1_calendar_events(year) for year in recent_years]
    
    results = await asyncio.gather(*([wrc_task] + f1_tasks), return_exceptions=True)
    
    recent_events = []
    for result in results:
        if isinstance(result, list):
            recent_events.extend(result)
        elif isinstance(result, Exception):
            logger.error(f"An error occurred during cache update: {result}")

    recent_events.sort(key=lambda x: x.start_date)
    
    cache["data"] = recent_events
    cache["timestamp"] = time.time()
    cache["is_updating"] = False
    logger.info(f"Recent cache updated with {len(recent_events)} events.")

async def periodic_cache_updater():
    """Runs the cache updater periodically."""
    while True:
        await update_recent_cache()
        await asyncio.sleep(CACHE_DURATION)

# --- API Endpoint ---

@router.get("", response_model=List[CalendarEvent])
async def get_calendar(
    year: Optional[int] = Query(None, description="Filter events by year"),
    categories: Optional[List[str]] = Query(None, description="Filter by a list of categories (e.g., WRC, F1). If not provided, all are returned.")
):
    """
    Get calendar events for various championships.
    Combines historic data from the database with recent data from the in-memory cache.
    """
    global cache
    
    if not cache["data"] and not cache["is_updating"]:
        # If cache is empty on first request, populate it synchronously for the user
        await update_recent_cache()
    
    # Wait if an update is in progress but cache is empty
    while not cache["data"] and cache["is_updating"]:
        await asyncio.sleep(0.5)

    # 1. Get recent events from cache
    recent_events = cache["data"]
    
    # 2. Get historic events from database
    try:
        historic_events = get_historic_events_from_db()
    except Exception as e:
        logger.error(f"Failed to fetch historic events from DB: {e}")
        historic_events = []
        
    # 3. Combine them
    all_events = historic_events + recent_events

    # Remove duplicates, preferring the more up-to-date 'recent' events
    seen_ids = set()
    unique_events = []
    for event in reversed(all_events):
        if event.id not in seen_ids:
            unique_events.append(event)
            seen_ids.add(event.id)
    unique_events.reverse() # Restore chronological order
    
    # Sort just to be sure
    unique_events.sort(key=lambda x: x.start_date)

    filtered_events = unique_events

    if categories:
        lower_categories = [cat.lower() for cat in categories]
        filtered_events = [event for event in filtered_events if event.category.lower() in lower_categories]

    if year is not None:
        filtered_events = [event for event in filtered_events if event.start_date.year == year]
    
    return filtered_events
