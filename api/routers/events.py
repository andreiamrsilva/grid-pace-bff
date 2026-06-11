from typing import List
from fastapi import APIRouter, HTTPException
import httpx

import sys
import os

# Adds the openWrc/src directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "openWrc", "src")))

from openwrc.clients.wrc_api_client import WrcApiClient
from models.event import Stage
import logging
import traceback

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/events",
    tags=["events"],
)

@router.get("/{event_id}/stages", response_model=List[Stage])
async def get_event_stages(event_id: int):
    """
    Get all stages for a given event, including the stage winner if available.
    """
    try:
        async with WrcApiClient() as client:
            # First, we need the event metadata to find the itinerary ID for the main rally.
            event_metadata = await client.get_event_metadata(event_id)
            if not event_metadata or not event_metadata.rallies:
                raise HTTPException(status_code=404, detail="Event not found or has no rallies.")

            # Assume the first rally is the main one.
            main_rally = event_metadata.rallies[0]
            itinerary_id = main_rally.itinerary_id
            rally_id = main_rally.rally_id

            # Fetch the itinerary which contains all stage details.
            itinerary = await client.get_event_itineraries(event_id, itinerary_id)
            if not itinerary or not itinerary.itinerary_legs:
                return []

            # Pre-fetch all entries (drivers) for this rally so we don't fetch them for every stage
            entries_dict = {}
            try:
                entries = await client.get_rally_entries(event_id, rally_id)
                for entry in entries:
                    entries_dict[entry.entry_id] = entry.driver.full_name
            except Exception as e:
                logger.warning(f"Could not pre-fetch entries for event {event_id}, rally {rally_id}: {e}")

            stages = []
            for leg in itinerary.itinerary_legs:
                for section in leg.itinerary_sections:
                    for stage_details in section.stages:
                        
                        # Find the corresponding StageStart control to get the start time
                        start_time = None
                        for control in section.controls:
                            if control.type == "StageStart" and control.stage_id == stage_details.stage_id:
                                start_time = control.first_car_due_date_time
                                break
                        
                        # Fetch the stage winner if the stage is completed
                        winner_name = None
                        if stage_details.status == "Completed":
                            try:
                                stage_results = await client.get_event_stage_results(
                                    event_id=event_id, 
                                    stage_id=stage_details.stage_id, 
                                    rally_id=rally_id
                                )
                                if stage_results:
                                    # The winner is the entry with position 1
                                    winner_entry_id = next((r.entry_id for r in stage_results if r.position == 1), None)
                                    if winner_entry_id and winner_entry_id in entries_dict:
                                        winner_name = entries_dict[winner_entry_id]
                            except httpx.HTTPStatusError as e:
                                # Ignore 404s, some stages might be marked completed but have no results published yet
                                if e.response.status_code != 404:
                                    logger.warning(f"HTTP error fetching results for stage {stage_details.stage_id}: {e}")
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
                                winner_name=winner_name
                            )
                        )
            
            # Sort stages by number
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