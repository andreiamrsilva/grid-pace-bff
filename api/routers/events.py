from typing import List, Optional
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone

import sys
import os

# Adds the openWrc/src directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "openWrc", "src")))

from models.event import Stage
from models.stage_times import StageStandings
from models.overall_standings import OverallStandings
from api.openf1_client import get_f1_event_sessions, fetch_f1_session_times, fetch_f1_overall_standings
from api.wrc_service import fetch_wrc_event_stages, fetch_wrc_stage_times, fetch_wrc_overall_standings
from api.redis_service import get_cached_data
from api.database_service import (
    get_stages_from_db, save_stages_to_db, 
    get_stage_times_from_db, save_stage_times_to_db,
    get_overall_standings_from_db, save_overall_standings_to_db
)
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
    db_stages = get_stages_from_db(event_id)
    if db_stages:
        return db_stages

    logger.debug(f"DB MISS for event stages: {event_id}. Fetching from source.")
    
    stages_to_cache = []
    is_past_event = False

    if category.lower() == "wrc":
        stages_to_cache = await fetch_wrc_event_stages(event_id)
        if stages_to_cache and stages_to_cache[-1].start_time and stages_to_cache[-1].status == "Completed":
            is_past_event = True
    
    elif category.lower() == "f1":
        stages_to_cache = await get_f1_event_sessions(event_id)
        if stages_to_cache and stages_to_cache[-1].status == "Completed":
            is_past_event = True
    else:
        raise HTTPException(status_code=404, detail="Category not supported.")

    if stages_to_cache and is_past_event:
        save_stages_to_db(event_id, stages_to_cache)

    return stages_to_cache

@router.get("/{category}/{event_id}/stages/{stage_id}/times", response_model=StageStandings)
async def get_stage_times(category: str, event_id: int, stage_id: int):
    """
    Get live or final timings for a specific stage/session.
    Prioritizes Redis for live data, then falls back to DB for completed data.
    """
    redis_key = f"live:times:{category.lower()}:{stage_id}"
    cached_live_data = await get_cached_data(redis_key)
    if cached_live_data:
        return StageStandings(**cached_live_data)
    
    db_times = get_stage_times_from_db(stage_id, event_id, category.upper())
    if db_times:
        return db_times

    logger.debug(f"Cache/DB MISS for stage times: {stage_id}. Fetching from source.")
    
    final_standings = None
    if category.lower() == "wrc":
        final_standings = await fetch_wrc_stage_times(event_id, stage_id)
    elif category.lower() == "f1":
        final_standings = await fetch_f1_session_times(stage_id, event_id)
        if final_standings:
            final_standings.is_live = False
    
    if final_standings and not final_standings.is_live and final_standings.standings:
        save_stage_times_to_db(stage_id, final_standings)
    
    return final_standings or StageStandings(stage_id=stage_id, event_id=event_id, category=category.upper(), is_live=False, standings=[])

@router.get("/{category}/{event_id}/overall", response_model=Optional[OverallStandings])
async def get_overall_standings(category: str, event_id: int):
    """
    Get the overall standings for an event.
    Prioritizes Redis for live data, then falls back to DB for completed data.
    """
    # 1. Check Redis for LIVE overall standings (populated by worker)
    redis_key = f"overall:{category.lower()}:{event_id}"
    cached_live_data = await get_cached_data(redis_key)
    if cached_live_data:
        logger.debug(f"Cache HIT for LIVE overall standings: {redis_key}")
        return OverallStandings(**cached_live_data)

    # 2. Check DB for COMPLETED data
    db_standings = get_overall_standings_from_db(event_id, category.upper())
    if db_standings:
        logger.debug(f"DB HIT for final overall standings: {event_id}")
        return db_standings

    # 3. Cache MISS: Fetch from source
    logger.debug(f"Cache/DB MISS for overall standings: {event_id}. Fetching from source.")
    
    standings_to_cache = None
    if category.lower() == "wrc":
        standings_to_cache = await fetch_wrc_overall_standings(event_id)
    elif category.lower() == "f1":
        standings_to_cache = await fetch_f1_overall_standings(event_id)
    
    if standings_to_cache and standings_to_cache.standings:
        save_overall_standings_to_db(event_id, standings_to_cache)
        
    return standings_to_cache
