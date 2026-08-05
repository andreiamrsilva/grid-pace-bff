from typing import Optional
from fastapi import APIRouter, Depends, Request, BackgroundTasks
from pydantic import BaseModel
import asyncio
import logging

from ingestion.service import (
    run_live_timing_ingestion,
    run_overall_standings_ingestion,
    run_championship_standings_ingestion,
    run_historic_archive,
    run_current_year_update,
    run_timeline_validation_cron,
    run_briefing_generation_cron,
)

logger = logging.getLogger(__name__)

from core.security import verify_cron_secret
from core.rate_limit import limiter

router = APIRouter(
    prefix="/cron", 
    tags=["Cron Jobs"],
    dependencies=[Depends(verify_cron_secret)]
)

class CronResponse(BaseModel):
    status: str

@router.get("/ingest-live-timing", response_model=CronResponse)
@limiter.limit("60/minute")
async def ingest_live_timing(request: Request):
    """Ingests live timing for all registered sports."""
    await run_live_timing_ingestion()
    return {"status": "success"}

@router.get("/ingest-overall-standings", response_model=CronResponse)
@limiter.limit("60/minute")
async def ingest_overall_standings(request: Request):
    """Ingests overall standings."""
    await run_overall_standings_ingestion()
    return {"status": "success"}

@router.get("/ingest-championship", response_model=CronResponse)
@limiter.limit("60/minute")
async def ingest_championship(request: Request):
    """Ingests championship standings."""
    await run_championship_standings_ingestion()
    return {"status": "success"}

@router.get("/archive-historic", response_model=CronResponse)
@limiter.limit("60/minute")
async def archive_historic(request: Request):
    """Archives historic events."""
    await run_historic_archive()
    return {"status": "success"}

@router.get("/update-current-year", response_model=CronResponse)
@limiter.limit("60/minute")
async def update_current_year(request: Request):
    """Updates events for the current year."""
    await run_current_year_update()
    return {"status": "success"}

@router.get("/validate-timeline-tweets", response_model=CronResponse)
@limiter.limit("60/minute")
async def validate_timeline_tweets(request: Request):
    """Validates missing tweets for recent stages and populates them."""
    await run_timeline_validation_cron()
    return {"status": "success"}

@router.get("/generate-briefings", response_model=CronResponse)
@limiter.limit("60/minute")
async def generate_briefings(request: Request, background_tasks: BackgroundTasks, force: bool = False, limit: Optional[int] = None):
    """Triggers AI briefing generation using Gemini API in a background task to prevent HTTP 30s timeouts."""
    background_tasks.add_task(run_briefing_generation_cron, force_update=force, batch_limit=limit)
    return {"status": "success", "message": "Briefing generation started in background"}
