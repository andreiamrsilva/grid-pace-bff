from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from datetime import datetime, timezone

import sys
import os

# Adds the openWrc/src directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "openWrc", "src")))

from models.event import Stage
from models.stage_times import StageStandings
from models.overall_standings import OverallStandings
from ingestion.openf1_client import get_f1_event_sessions, fetch_f1_session_times, fetch_f1_overall_standings
from ingestion.wrc_client import fetch_wrc_event_stages, fetch_wrc_stage_times, fetch_wrc_overall_standings
from core.redis_service import get_cached_data
from core.database_service import (
    get_stages_from_db, save_stages_to_db, 
    get_stage_times_from_db, save_stage_times_to_db,
    get_overall_standings_from_db, save_overall_standings_to_db
)
import logging

logger = logging.getLogger(__name__)

from core.security import verify_client_token, verify_app_check_token
from core.rate_limit import limiter

router = APIRouter(
    prefix="/events",
    tags=["events"],
    dependencies=[Depends(verify_client_token), Depends(verify_app_check_token)],
)

@router.get("/{category}/{event_id}/stages", response_model=List[Stage])
@limiter.limit("60/minute")
async def get_event_details(request: Request, category: str, event_id: int):
    """
    Get all stages/sessions for a given event, using a multi-layer caching strategy.
    """
    if category.lower() not in ("wrc", "f1"):
        raise HTTPException(status_code=404, detail="Category not supported.")

    redis_key = f"event:{category.lower()}:{event_id}:stages"
    
    # 1. Try Redis first (for active events populated by the worker)
    cached_stages = await get_cached_data(redis_key)
    if cached_stages:
        logger.debug(f"Redis HIT for event stages: {redis_key}")
        return [Stage(**stage_data) for stage_data in cached_stages]

    # 2. Try DB cache (for completed, historic events)
    db_stages = await get_stages_from_db(event_id)
    if db_stages:
        if len(db_stages) > 0 and db_stages[-1].status == "Completed":
            logger.debug(f"DB HIT for event stages (Completed): {event_id}")
            return db_stages
        else:
            logger.debug(f"DB stages found but event not completed. Will re-fetch: {event_id}")

    # 3. Cache MISS: Fetch from the source
    logger.debug(f"Cache/DB MISS for event stages: {event_id}. Fetching from source.")
    
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

    # 4. Store in the permanent DB cache (always update stages so we have them)
    if stages_to_cache:
        if not is_past_event:
            from core.redis_service import set_cached_data
            await set_cached_data(redis_key, [s.model_dump(mode='json') for s in stages_to_cache], expiration_seconds=120)
        await save_stages_to_db(event_id, stages_to_cache)

    return stages_to_cache

@router.get("/{category}/{event_id}/stages/{stage_id}/times", response_model=StageStandings)
@limiter.limit("60/minute")
async def get_stage_times(
    request: Request,
    category: str, 
    event_id: int, 
    stage_id: int, 
    last_sync_time: Optional[datetime] = None
):
    """
    Get live or final timings for a specific stage/session.
    Prioritizes Redis for live data, then falls back to DB for completed data.
    Supports Smart Polling via last_sync_time: returns HTTP 304 if no new data is available.
    """
    # Helper to check if data is modified
    def is_not_modified(data_last_updated: Optional[datetime]) -> bool:
        if not last_sync_time or not data_last_updated:
            return False
        # Ensure UTC comparisons
        sync_time = last_sync_time if last_sync_time.tzinfo else last_sync_time.replace(tzinfo=timezone.utc)
        updated_time = data_last_updated if data_last_updated.tzinfo else data_last_updated.replace(tzinfo=timezone.utc)
        return updated_time <= sync_time

    redis_key = f"live:times:{category.lower()}:{stage_id}"
    cached_live_data = await get_cached_data(redis_key)
    
    if cached_live_data:
        standings = StageStandings(**cached_live_data)
        if is_not_modified(standings.last_updated):
            from fastapi.responses import Response
            return Response(status_code=304)
        return standings
    
    db_times = await get_stage_times_from_db(stage_id, event_id, category.upper())
    if db_times:
        if is_not_modified(db_times.last_updated):
            from fastapi.responses import Response
            return Response(status_code=304)
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
        # Set last_updated if not set by ingestion
        if not final_standings.last_updated:
            final_standings.last_updated = datetime.now(timezone.utc)
        await save_stage_times_to_db(stage_id, final_standings)
    
    if final_standings and is_not_modified(final_standings.last_updated):
        from fastapi.responses import Response
        return Response(status_code=304)
        
    return final_standings or StageStandings(stage_id=stage_id, event_id=event_id, category=category.upper(), is_live=False, standings=[])

@router.get("/{category}/{event_id}/overall", response_model=Optional[OverallStandings])
@limiter.limit("60/minute")
async def get_overall_standings(request: Request, category: str, event_id: int):
    """
    Get the overall standings for an event.
    Prioritizes Redis for live data, then falls back to DB for completed data.
    """
    redis_key = f"overall:{category.lower()}:{event_id}"
    cached_live_data = await get_cached_data(redis_key)
    if cached_live_data:
        return OverallStandings(**cached_live_data)

    try:
        db_standings = await get_overall_standings_from_db(event_id, category.upper())
        if db_standings:
            return db_standings
    except Exception as e:
        logger.warning(f"Error fetching overall standings from DB for event {event_id}: {e}")

    logger.debug(f"Cache/DB MISS for overall standings: {event_id}. Fetching from source.")
    
    standings_to_cache = None
    if category.lower() == "wrc":
        standings_to_cache = await fetch_wrc_overall_standings(event_id)
    elif category.lower() == "f1":
        standings_to_cache = await fetch_f1_overall_standings(event_id)
    
    if standings_to_cache is None:
        raise HTTPException(
            status_code=502,
            detail=f"Data source unavailable for {category.upper()} overall standings. The session might be live and restricted, or the upstream API failed."
        )

    if standings_to_cache and standings_to_cache.standings:
        await save_overall_standings_to_db(event_id, standings_to_cache)
        
    return standings_to_cache

from models.event_briefing import EventBriefing
from core.briefing_service import get_event_briefing

@router.get("/{category}/{event_id}/briefing", response_model=EventBriefing)
@limiter.limit("60/minute")
async def get_event_briefing_endpoint(
    request: Request,
    category: str,
    event_id: int,
    language: str = Query("pt", description="Language code for briefing content (e.g. 'pt', 'en'). Defaults to 'pt'.")
):
    """
    Get comprehensive pre-event briefing for an F1 or WRC event.
    Provides weather forecast, circuit/rally metadata, surface type, total distance,
    laps count (F1), tactical briefing, last winner, event record, and track map layout.
    Supports language localization ('pt', 'en').
    """
    if category.lower() not in ("wrc", "f1"):
        raise HTTPException(status_code=404, detail="Category not supported.")

    try:
        briefing = await get_event_briefing(category, event_id, language=language)
        if not briefing:
            raise HTTPException(status_code=404, detail=f"Briefing not found for event {event_id}.")
        return briefing
    except Exception as e:
        logger.error(f"Error fetching event briefing for {category} event {event_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve event briefing.")

