from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
import httpx
import time
import asyncio

import sys
import os

# Adds the openWrc/src directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "openWrc", "src")))

from openwrc.clients.wrc_api_client import WrcApiClient
from models.calendar import CalendarEvent
from api.utils import get_manufacturer_logo_url
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
CACHE_DURATION = 300  # Cache duration in seconds (5 minutes)

async def update_calendar_cache():
    """Fetches full calendar data and updates the cache."""
    global cache
    
    if cache["is_updating"]:
        return
        
    cache["is_updating"] = True
    logger.info("Starting calendar cache background update.")
    calendar_events = []

    try:
        async with WrcApiClient() as client:
            seasons = await client.get_seasons()

            for season in seasons:
                season_detail = await client.get_season_detail(season.season_id)
                
                if not season_detail or not season_detail.season_rounds:
                    continue
                
                for round_info in season_detail.season_rounds:
                    if not round_info.event:
                        continue
                        
                    country_name = "Unknown"
                    country_image_url = None
                    if hasattr(round_info.event, "country") and round_info.event.country:
                        country_name = round_info.event.country.name
                        if hasattr(round_info.event.country, "iso2") and round_info.event.country.iso2:
                            country_image_url = f"https://flagcdn.com/w320/{round_info.event.country.iso2.lower()}.png"

                    current_leader = None
                    current_leader_manufacturer_logo_url = None
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
                                            current_leader_manufacturer_logo_url = get_manufacturer_logo_url(leader_entry.manufacturer.name)

                    except httpx.HTTPStatusError as e:
                        if e.response.status_code != 404:
                            logger.warning(f"HTTP error fetching leader for event {round_info.event.event_id}: {e}")
                    except Exception as e:
                        logger.warning(f"Error fetching leader for event {round_info.event.event_id}: {e}")
                        
                    calendar_events.append(
                        CalendarEvent(
                            id=round_info.event.event_id,
                            name=round_info.event.name,
                            country=country_name,
                            country_image_url=country_image_url,
                            start_date=round_info.event.start_date,
                            finish_date=round_info.event.finish_date,
                            current_leader=current_leader,
                            current_leader_manufacturer_logo_url=current_leader_manufacturer_logo_url,
                        )
                    )
        
        # Update cache atomically
        cache["data"] = calendar_events
        cache["timestamp"] = time.time()
        logger.info("Calendar cache updated successfully.")
                    
    except Exception as e:
        logger.error(f"Error updating calendar cache: {e}")
        logger.error(traceback.format_exc())
    finally:
        cache["is_updating"] = False

async def periodic_cache_updater():
    """Runs continuously in the background to update the cache every 5 minutes."""
    while True:
        await update_calendar_cache()
        await asyncio.sleep(CACHE_DURATION)

@router.get("", response_model=List[CalendarEvent])
async def get_calendar(
    year: Optional[int] = Query(None, description="Filter events by year"),
):
    """
    Get calendar events.
    This endpoint returns data from memory, which is updated in the background.
    """
    global cache
    
    # If the cache is empty but being updated (on startup), wait for it to finish.
    while cache["is_updating"] and not cache["data"]:
        await asyncio.sleep(0.5)
    
    if not cache["data"] and not cache["is_updating"]:
        await update_calendar_cache()

    filtered_events = cache["data"]
    
    if year is not None:
        filtered_events = [event for event in filtered_events if event.start_date.year == year]
    
    return filtered_events