from typing import List, Optional
from fastapi import APIRouter, HTTPException
import httpx
import asyncio
from datetime import datetime, timezone

import sys
import os

# Adds the openWrc/src directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "openWrc", "src")))

from openwrc.clients.wrc_api_client import WrcApiClient
from models.event import Stage
from models.stage_times import StageStandings, DriverTime
from api.utils import get_logo_path
from api.openf1_client import get_f1_event_sessions
from api.redis_service import get_cached_data, set_cached_data
import logging
import traceback

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/events",
    tags=["events"],
)

def format_ms_to_time(ms: int) -> str:
    """Converts milliseconds to a formatted string (MM:SS.m)"""
    if ms is None:
        return None
    
    prefix = ""
    if ms < 0:
        prefix = "+"
        ms = abs(ms)
        
    total_seconds = ms / 1000.0
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    tenths = int((total_seconds * 10) % 10)
    
    if minutes > 0:
        return f"{prefix}{minutes:02d}:{seconds:02d}.{tenths}"
    else:
        return f"{prefix}{seconds:02d}.{tenths}"

async def _fetch_wrc_event_stages(event_id: int) -> List[Stage]:
    """Internal function to fetch WRC stages from the source."""
    try:
        async with WrcApiClient() as client:
            event_metadata = await client.get_event_metadata(event_id)
            if not event_metadata or not event_metadata.rallies:
                return []

            main_rally = event_metadata.rallies[0]
            itinerary = await client.get_event_itineraries(event_id, main_rally.itinerary_id)
            if not itinerary or not itinerary.itinerary_legs:
                return []

            entries = await client.get_rally_entries(event_id, main_rally.rally_id)
            entries_dict = {entry.entry_id: entry for entry in entries}

            stages = []
            for leg in itinerary.itinerary_legs:
                for section in leg.itinerary_sections:
                    for stage_details in section.stages:
                        start_time = next((c.first_car_due_date_time for c in section.controls if c.type == "StageStart" and c.stage_id == stage_details.stage_id), None)
                        
                        winner_name, winner_logo_path, winner_time = None, None, None
                        if stage_details.status == "Completed":
                            try:
                                stage_results = await client.get_event_stage_results(event_id, stage_details.stage_id, main_rally.rally_id)
                                if stage_results:
                                    winner_result = next((r for r in stage_results if r.position == 1), None)
                                    if winner_result and winner_result.entry_id in entries_dict:
                                        winner_entry = entries_dict[winner_result.entry_id]
                                        winner_name = winner_entry.driver.full_name
                                        if hasattr(winner_entry, 'manufacturer') and winner_entry.manufacturer:
                                            winner_logo_path = get_logo_path(winner_entry.manufacturer.name)
                                        winner_time = format_ms_to_time(winner_result.stage_time_ms)
                            except Exception:
                                pass
                                
                        stages.append(Stage(id=stage_details.stage_id, name=stage_details.name, number=stage_details.number, distance=stage_details.distance, start_time=start_time, status=stage_details.status, is_live=stage_details.status == "Running", winner_name=winner_name, winner_logo_path=winner_logo_path, winner_time=winner_time))
            
            stages.sort(key=lambda s: s.number)
            return stages
    except Exception as e:
        logger.error(f"Error fetching WRC stages from source: {e}")
        return []

async def get_wrc_stage_times(event_id: int, stage_id: int) -> Optional[StageStandings]:
    """
    Fetches the live or final times for a specific WRC stage directly from the source.
    """
    try:
        async with WrcApiClient() as client:
            event_metadata = await client.get_event_metadata(event_id)
            if not event_metadata or not event_metadata.rallies:
                return None
            rally_id = event_metadata.rallies[0].rally_id

            entries_dict = {}
            entries = await client.get_rally_entries(event_id, rally_id)
            for entry in entries:
                entries_dict[entry.entry_id] = entry

            finished_drivers = []
            finished_entry_ids = set()
            try:
                stage_results = await client.get_event_stage_results(event_id, stage_id, rally_id)
                stage_results.sort(key=lambda x: x.position if x.position else 999)
                
                for result in stage_results:
                    if result.entry_id in entries_dict:
                        entry = entries_dict[result.entry_id]
                        logo_path = get_logo_path(entry.manufacturer.name) if hasattr(entry, 'manufacturer') and entry.manufacturer else None
                        
                        finished_drivers.append(DriverTime(
                            entry_id=result.entry_id,
                            driver_name=entry.driver.full_name,
                            logo_path=logo_path,
                            status="Finished",
                            time=format_ms_to_time(result.stage_time_ms),
                            diff_to_first=format_ms_to_time(result.diff_first_ms) if result.diff_first_ms else None,
                            position=result.position
                        ))
                        finished_entry_ids.add(result.entry_id)
            except Exception as e:
                logger.warning(f"Could not fetch final results for stage {stage_id}: {e}")

            on_track_drivers = []
            try:
                split_results = await client.get_rally_stage_split_time_results(event_id, rally_id, stage_id)
                
                entry_splits = {}
                for split in split_results:
                    if split.entry_id not in entry_splits:
                        entry_splits[split.entry_id] = []
                    entry_splits[split.entry_id].append(split)
                
                for e_id, splits in entry_splits.items():
                    if e_id in finished_entry_ids:
                        continue
                        
                    if e_id in entries_dict:
                        entry = entries_dict[e_id]
                        logo_path = get_logo_path(entry.manufacturer.name) if hasattr(entry, 'manufacturer') and entry.manufacturer else None
                        
                        splits.sort(key=lambda x: x.elapsed_duration_ms, reverse=True)
                        latest_split = splits[0]
                        
                        on_track_drivers.append(DriverTime(
                            entry_id=e_id,
                            driver_name=entry.driver.full_name,
                            logo_path=logo_path,
                            status="OnTrack",
                            time=format_ms_to_time(latest_split.elapsed_duration_ms),
                            last_split_id=latest_split.split_point_id
                        ))
            except Exception as e:
                logger.warning(f"Could not fetch split times for stage {stage_id}: {e}")

            on_track_drivers.sort(key=lambda x: x.last_split_id if x.last_split_id else 0, reverse=True)
            
            all_standings = finished_drivers + on_track_drivers
            is_live = len(on_track_drivers) > 0

            return StageStandings(
                stage_id=stage_id,
                event_id=event_id,
                category="WRC",
                is_live=is_live,
                standings=all_standings
            )

    except Exception as e:
        logger.error(f"Error fetching times: {e}")
        return None

@router.get("/{category}/{event_id}/stages", response_model=List[Stage])
async def get_event_details(category: str, event_id: int):
    """
    Get all stages/sessions for a given event, using a read-through cache.
    """
    redis_key = f"event:{category.lower()}:{event_id}:stages"
    
    cached_stages = await get_cached_data(redis_key)
    if cached_stages:
        logger.debug(f"Cache HIT for event stages: {redis_key}")
        return [Stage(**stage_data) for stage_data in cached_stages]

    logger.debug(f"Cache MISS for event stages: {redis_key}. Fetching from source.")
    
    stages_to_cache = []
    is_past_event = False

    if category.lower() == "wrc":
        stages_to_cache = await _fetch_wrc_event_stages(event_id)
        if stages_to_cache and stages_to_cache[-1].start_time:
            is_past_event = stages_to_cache[-1].start_time < datetime.now(timezone.utc)
    
    elif category.lower() == "f1":
        stages_to_cache = await get_f1_event_sessions(event_id)
        if stages_to_cache and stages_to_cache[-1].start_time:
            is_past_event = stages_to_cache[-1].start_time < datetime.now(timezone.utc)
    else:
        raise HTTPException(status_code=404, detail="Category not supported.")

    if stages_to_cache:
        ttl = 2592000 if is_past_event else 300 # 30 days for past, 5 mins for active
        await set_cached_data(redis_key, [stage.model_dump(mode='json') for stage in stages_to_cache], expiration_seconds=ttl)

    return stages_to_cache

@router.get("/{category}/{event_id}/stages/{stage_id}/times", response_model=StageStandings)
async def get_stage_times(category: str, event_id: int, stage_id: int):
    """
    Get live or final timings for a specific stage/session from the Redis cache.
    """
    redis_key = f"live:times:{category.lower()}:{stage_id}"
    cached_data = await get_cached_data(redis_key)
    
    if cached_data:
        return StageStandings(**cached_data)
    
    logger.warning(f"Cache MISS for live times: {redis_key}. Returning empty. Worker might be down or stage not live.")
    return StageStandings(stage_id=stage_id, event_id=event_id, category=category.upper(), is_live=False, standings=[])
