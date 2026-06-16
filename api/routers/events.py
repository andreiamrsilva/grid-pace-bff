from typing import List, Optional
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone

import sys
import os

# Adds the openWrc/src directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "openWrc", "src")))

from models.event import Stage
from models.stage_times import StageStandings
from api.openf1_client import get_f1_event_sessions, fetch_f1_session_times
from api.wrc_service import fetch_wrc_event_stages, fetch_wrc_stage_times
from api.redis_service import get_cached_data
from api.database_service import get_stages_from_db, save_stages_to_db, get_stage_times_from_db, save_stage_times_to_db
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/events",
    tags=["events"],
)

@router.get("/{category}/{event_id}/stages", response_model=List[Stage])
async def get_event_details(category: str, event_id: int):
    """
    Get all stages/sessions for a given event, using a database-first caching strategy.
    """
    # 1. Try to get from DB cache first
    db_stages = get_stages_from_db(event_id)
    if db_stages:
        logger.debug(f"DB HIT for event stages: {event_id}")
        return db_stages

    # 2. Cache MISS: Fetch from the source
    logger.debug(f"DB MISS for event stages: {event_id}. Fetching from source.")
    
    stages_to_cache = []
    is_past_event = False

    if category.lower() == "wrc":
        stages_to_cache = await fetch_wrc_event_stages(event_id)
        if stages_to_cache and stages_to_cache[-1].start_time:
            if stages_to_cache[-1].status == "Completed":
                is_past_event = True
    
    elif category.lower() == "f1":
        stages_to_cache = await get_f1_event_sessions(event_id)
        if stages_to_cache and stages_to_cache[-1].status == "Completed":
            is_past_event = True
    else:
        raise HTTPException(status_code=404, detail="Category not supported.")

    # 3. If the event is over and we have data, store in the permanent DB cache
    if stages_to_cache and is_past_event:
        save_stages_to_db(event_id, stages_to_cache)

    return stages_to_cache

@router.get("/{category}/{event_id}/stages/{stage_id}/times", response_model=StageStandings)
async def get_stage_times(category: str, event_id: int, stage_id: int):
    """
    Get live or final timings for a specific stage/session.
    Prioritizes Redis for live data, then falls back to DB for completed data.
    """
    # 1. Check Redis for LIVE data (populated by worker)
    redis_key = f"live:times:{category.lower()}:{stage_id}"
    cached_live_data = await get_cached_data(redis_key)
    if cached_live_data:
        logger.debug(f"Cache HIT for LIVE times: {redis_key}")
        return StageStandings(**cached_live_data)
    
    # 2. Check DB for COMPLETED data
    db_times = get_stage_times_from_db(stage_id, event_id, category.upper())
    if db_times:
        logger.debug(f"DB HIT for final times: {stage_id}")
        return db_times

    # 3. Cache MISS: Fetch from source
    logger.debug(f"Cache/DB MISS for stage times: {stage_id}. Fetching from source.")
    
    final_standings = None
    if category.lower() == "wrc":
        final_standings = await fetch_wrc_stage_times(event_id, stage_id)
    elif category.lower() == "f1":
        final_standings = await fetch_f1_session_times(stage_id, event_id)
        if final_standings:
            final_standings.is_live = False
            for d in final_standings.standings:
                d.status = "Finished"
    
    # Only save to DB if the fetch was successful and the stage is actually completed
    if final_standings and not final_standings.is_live and final_standings.standings:
        save_stage_times_to_db(stage_id, final_standings)
    
    return final_standings or StageStandings(stage_id=stage_id, event_id=event_id, category=category.upper(), is_live=False, standings=[])
