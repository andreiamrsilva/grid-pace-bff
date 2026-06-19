from fastapi import APIRouter
from pydantic import BaseModel
import asyncio
import logging

from ingestion.service import (
    run_live_timing_ingestion,
    run_overall_standings_ingestion,
    run_championship_standings_ingestion,
    run_historic_archive,
    run_current_year_update,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cron", tags=["Cron Jobs"])

class CronResponse(BaseModel):
    status: str

@router.post("/ingest-live-timing", response_model=CronResponse)
async def ingest_live_timing():
    """Ingests live timing for all registered sports."""
    await run_live_timing_ingestion()
    return {"status": "success"}

@router.post("/ingest-overall-standings", response_model=CronResponse)
async def ingest_overall_standings():
    """Ingests overall standings."""
    await run_overall_standings_ingestion()
    return {"status": "success"}

@router.post("/ingest-championship", response_model=CronResponse)
async def ingest_championship():
    """Ingests championship standings."""
    await run_championship_standings_ingestion()
    return {"status": "success"}

@router.post("/archive-historic", response_model=CronResponse)
async def archive_historic():
    """Archives historic events."""
    await run_historic_archive()
    return {"status": "success"}

@router.post("/update-current-year", response_model=CronResponse)
async def update_current_year():
    """Updates events for the current year."""
    await run_current_year_update()
    return {"status": "success"}
