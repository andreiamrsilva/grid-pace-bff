from typing import List, Optional
from fastapi import APIRouter, HTTPException
import httpx
import asyncio

import sys
import os

# Adds the openWrc/src directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "openWrc", "src")))

from openwrc.clients.wrc_api_client import WrcApiClient
from models.event import Stage
from models.stage_times import StageStandings, DriverTime
from api.utils import get_logo_path
from api.f1_client import get_f1_event_sessions
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
    
    # Handle negative times (e.g., diff to first)
    prefix = ""
    if ms < 0:
        prefix = "+" # In rallying, diff is usually shown as positive gap
        ms = abs(ms)
        
    total_seconds = ms / 1000.0
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    tenths = int((total_seconds * 10) % 10)
    
    if minutes > 0:
        return f"{prefix}{minutes:02d}:{seconds:02d}.{tenths}"
    else:
        return f"{prefix}{seconds:02d}.{tenths}"

async def get_wrc_event_stages(event_id: int) -> List[Stage]:
    """
    Fetches all stages for a given WRC event.
    """
    try:
        async with WrcApiClient() as client:
            event_metadata = await client.get_event_metadata(event_id)
            if not event_metadata or not event_metadata.rallies:
                raise HTTPException(status_code=404, detail="Event not found or has no rallies.")

            main_rally = event_metadata.rallies[0]
            itinerary_id = main_rally.itinerary_id
            rally_id = main_rally.rally_id

            itinerary = await client.get_event_itineraries(event_id, itinerary_id)
            if not itinerary or not itinerary.itinerary_legs:
                return []

            entries_dict = {}
            try:
                entries = await client.get_rally_entries(event_id, rally_id)
                for entry in entries:
                    entries_dict[entry.entry_id] = entry
            except Exception as e:
                logger.warning(f"Could not pre-fetch entries for event {event_id}, rally {rally_id}: {e}")

            stages = []
            for leg in itinerary.itinerary_legs:
                for section in leg.itinerary_sections:
                    for stage_details in section.stages:
                        start_time = None
                        for control in section.controls:
                            if control.type == "StageStart" and control.stage_id == stage_details.stage_id:
                                start_time = control.first_car_due_date_time
                                break
                        
                        winner_name = None
                        winner_logo_path = None
                        winner_time = None
                        if stage_details.status == "Completed":
                            try:
                                stage_results = await client.get_event_stage_results(
                                    event_id=event_id, 
                                    stage_id=stage_details.stage_id, 
                                    rally_id=rally_id
                                )
                                if stage_results:
                                    winner_result = next((r for r in stage_results if r.position == 1), None)
                                    if winner_result and winner_result.entry_id in entries_dict:
                                        winner_entry = entries_dict[winner_result.entry_id]
                                        winner_name = winner_entry.driver.full_name
                                        if hasattr(winner_entry, 'manufacturer') and winner_entry.manufacturer:
                                            winner_logo_path = get_logo_path(winner_entry.manufacturer.name)
                                        winner_time = format_ms_to_time(winner_result.stage_time_ms)
                            except Exception as e:
                                logger.warning(f"Error fetching results for stage {stage_details.stage_id}: {e}")
                                
                        stages.append(
                            Stage(
                                id=stage_details.stage_id,
                                name=stage_details.name,
                                number=stage_details.number,
                                distance=stage_details.distance,
                                start_time=start_time,
                                status=stage_details.status,
                                is_live=stage_details.status == "Running",
                                winner_name=winner_name,
                                winner_logo_path=winner_logo_path,
                                winner_time=winner_time
                            )
                        )
            
            stages.sort(key=lambda s: s.number)
            return stages

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Event with ID {event_id} not found.")
        logger.error(f"HTTP error fetching stages for event {event_id}: {e}")
        raise HTTPException(status_code=502, detail="Error communicating with external data source.")
    except Exception as e:
        logger.error(f"Unexpected error fetching stages for event {event_id}: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


async def get_wrc_stage_times(event_id: int, stage_id: int) -> StageStandings:
    """
    Fetches the live or final times for a specific WRC stage.
    Builds a list of drivers who have finished and drivers currently on track.
    """
    try:
        async with WrcApiClient() as client:
            # 1. Get Rally ID
            event_metadata = await client.get_event_metadata(event_id)
            if not event_metadata or not event_metadata.rallies:
                raise HTTPException(status_code=404, detail="Event not found")
            rally_id = event_metadata.rallies[0].rally_id

            # 2. Get Entries
            entries_dict = {}
            entries = await client.get_rally_entries(event_id, rally_id)
            for entry in entries:
                entries_dict[entry.entry_id] = entry

            # 3. Get Final Results for the stage
            finished_drivers = []
            finished_entry_ids = set()
            try:
                stage_results = await client.get_event_stage_results(event_id, stage_id, rally_id)
                # Sort by position
                stage_results.sort(key=lambda x: x.position if x.position else 999)
                
                for result in stage_results:
                    if result.entry_id in entries_dict:
                        entry = entries_dict[result.entry_id]
                        logo_path = get_logo_path(entry.manufacturer.name) if hasattr(entry, 'manufacturer') and entry.manufacturer else None
                        
                        finished_drivers.append(DriverTime(
                            entry_id=result.entry_id,
                            driver_name=entry.driver.full_name,
                            manufacturer_logo_path=logo_path,
                            status="Finished",
                            time=format_ms_to_time(result.stage_time_ms),
                            diff_to_first=format_ms_to_time(result.diff_first_ms) if result.diff_first_ms else None,
                            position=result.position
                        ))
                        finished_entry_ids.add(result.entry_id)
            except Exception as e:
                logger.warning(f"Could not fetch final results for stage {stage_id}: {e}")

            # 4. Get Split Times for drivers On Track
            on_track_drivers = []
            try:
                split_results = await client.get_rally_stage_split_time_results(event_id, rally_id, stage_id)
                
                # Group splits by entry
                entry_splits = {}
                for split in split_results:
                    if split.entry_id not in entry_splits:
                        entry_splits[split.entry_id] = []
                    entry_splits[split.entry_id].append(split)
                
                for e_id, splits in entry_splits.items():
                    # If they are already in the finished list, ignore their splits
                    if e_id in finished_entry_ids:
                        continue
                        
                    if e_id in entries_dict:
                        entry = entries_dict[e_id]
                        logo_path = get_logo_path(entry.manufacturer.name) if hasattr(entry, 'manufacturer') and entry.manufacturer else None
                        
                        # Find their latest split
                        splits.sort(key=lambda x: x.elapsed_duration_ms, reverse=True)
                        latest_split = splits[0]
                        
                        on_track_drivers.append(DriverTime(
                            entry_id=e_id,
                            driver_name=entry.driver.full_name,
                            manufacturer_logo_path=logo_path,
                            status="OnTrack",
                            time=format_ms_to_time(latest_split.elapsed_duration_ms),
                            last_split_id=latest_split.split_point_id
                        ))
            except Exception as e:
                logger.warning(f"Could not fetch split times for stage {stage_id}: {e}")

            # 5. Combine and Sort
            # Finished drivers are already sorted by position.
            # On track drivers could be sorted by last_split_id (approximation of distance) or elapsed time
            on_track_drivers.sort(key=lambda x: x.last_split_id if x.last_split_id else 0, reverse=True)
            
            all_standings = finished_drivers + on_track_drivers
            
            # Determine if the stage is currently live
            is_live = len(on_track_drivers) > 0

            return StageStandings(
                stage_id=stage_id,
                event_id=event_id,
                category="WRC",
                is_live=is_live,
                standings=all_standings
            )

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Data not found.")
        raise HTTPException(status_code=502, detail="External API error.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching times: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.get("/{category}/{event_id}/stages", response_model=List[Stage])
async def get_event_details(category: str, event_id: int):
    """
    Get all stages/sessions for a given event, based on its category.
    """
    if category.lower() == "wrc":
        return await get_wrc_event_stages(event_id)
    elif category.lower() == "f1":
        # The F1 event_id is YYYYRR (e.g., 202401). We need to extract year and round.
        try:
            year = int(str(event_id)[:4])
            round_number = int(str(event_id)[4:])
            return await get_f1_event_sessions(year, round_number)
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="Invalid F1 event ID format. Expected YYYYRR.")
    else:
        raise HTTPException(status_code=404, detail="Category not supported.")

@router.get("/{category}/{event_id}/stages/{stage_id}/times", response_model=StageStandings)
async def get_stage_times(category: str, event_id: int, stage_id: int):
    """
    Get live or final timings for a specific stage/session.
    """
    if category.lower() == "wrc":
        return await get_wrc_stage_times(event_id, stage_id)
    elif category.lower() == "f1":
        # Placeholder for future F1 live timing implementation
        return StageStandings(
            stage_id=stage_id,
            event_id=event_id,
            category="F1",
            is_live=False,
            standings=[]
        )
    else:
        raise HTTPException(status_code=404, detail="Category not supported.")
