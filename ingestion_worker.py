import asyncio
import logging
import httpx
from datetime import datetime, date
import sys
import os

# Add project root and openWrc src to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'openWrc', 'src')))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger("IngestionWorker")

from api.redis_service import set_cached_data, check_redis_connection, close_redis_connection
from api.database_service import get_all_events_from_db
from api.wrc_service import fetch_wrc_event_stages, fetch_wrc_stage_times, fetch_wrc_overall_standings
from api.openf1_client import get_f1_event_sessions, fetch_f1_overall_standings, fetch_f1_championship_standings, fetch_f1_team_championship_standings, OPENF1_API_URL
from models.stage_times import StageStandings, DriverTime
from models.overall_standings import OverallStandings
from api.utils import get_logo_path

POLL_INTERVAL_SECONDS = 15
OVERALL_POLL_INTERVAL_SECONDS = 60
CHAMPIONSHIP_POLL_INTERVAL_SECONDS = 3600 # 1 hour

def calculate_position_changes(old_standings: dict, new_standings: OverallStandings) -> OverallStandings:
    # ... (implementation is the same)
    pass

async def find_live_stages(category: str):
    """
    Scans the calendar from the DB to find events that are currently active.
    Then, fetches their stages to find which are 'Running'.
    """
    try:
        all_events = get_all_events_from_db()
        today = date.today()

        active_events = [e for e in all_events if e.category.lower() == category and e.start_date <= today <= e.finish_date]

        if not active_events:
            return []

        live_stages = []
        for event in active_events:
            if category == 'wrc':
                stages = await fetch_wrc_event_stages(event.id)
                live_stages.extend([(event.id, s.id) for s in stages if s.is_live])
            elif category == 'f1':
                sessions = await get_f1_event_sessions(event.id)
                live_stages.extend([(event.id, s.id) for s in sessions if s.is_live])

        return live_stages
    except Exception as e:
        logger.error(f"Error finding live stages for {category}: {e}")
        return []

async def wrc_ingestion_task():
    """The core task for ingesting WRC live timing data."""
    live_stages = await find_live_stages('wrc')

    if not live_stages:
        return

    for event_id, stage_id in live_stages:
        try:
            stage_standings = await fetch_wrc_stage_times(event_id, stage_id)
            if stage_standings:
                redis_key = f"live:times:wrc:{stage_id}"
                await set_cached_data(redis_key, stage_standings.model_dump(mode='json'), expiration_seconds=60)
        except Exception as e:
            logger.error(f"Error during WRC ingestion for Stage {stage_id}: {e}")

async def get_f1_live_timing(client: httpx.AsyncClient, session_key: int, meeting_key: int) -> StageStandings:
    # ... (implementation is the same)
    pass

async def f1_ingestion_task():
    """The core task for ingesting F1 live timing data."""
    live_sessions = await find_live_stages('f1')

    if not live_sessions:
        return

    async with httpx.AsyncClient(timeout=10.0) as client:
        for meeting_key, session_key in live_sessions:
            try:
                standings = await get_f1_live_timing(client, session_key, meeting_key)
                if standings:
                    redis_key = f"live:times:f1:{session_key}"
                    await set_cached_data(redis_key, standings.model_dump(mode='json'), expiration_seconds=60)
            except Exception as e:
                logger.error(f"Error during F1 ingestion for Session {session_key}: {e}")

async def overall_standings_ingestion_task():
    # ... (implementation is the same)
    pass

async def championship_standings_ingestion_task():
    """Periodically fetches and caches the championship standings for the current year."""
    while True:
        logger.info("Running championship standings cache update...")
        try:
            current_year = datetime.now().year

            # --- F1 ---
            f1_drivers = await fetch_f1_championship_standings(current_year)
            if f1_drivers:
                await set_cached_data(f"championship:drivers:f1:{current_year}", f1_drivers.model_dump(mode='json'), expiration_seconds=CHAMPIONSHIP_POLL_INTERVAL_SECONDS * 2)

            f1_teams = await fetch_f1_team_championship_standings(current_year)
            if f1_teams:
                await set_cached_data(f"championship:teams:f1:{current_year}", f1_teams.model_dump(mode='json'), expiration_seconds=CHAMPIONSHIP_POLL_INTERVAL_SECONDS * 2)

        except Exception as e:
            logger.error(f"Error updating championship standings cache: {e}")

        await asyncio.sleep(CHAMPIONSHIP_POLL_INTERVAL_SECONDS)

async def main_loop():
    """The main loop of the ingestion worker."""
    logger.info("--- Ingestion Worker Starting ---")
    
    if not await check_redis_connection():
        logger.error("Could not connect to Redis. Aborting worker.")
        return

    # Start background tasks
    overall_task = asyncio.create_task(overall_standings_ingestion_task())
    championship_task = asyncio.create_task(championship_standings_ingestion_task())

    try:
        while True:
            try:
                await asyncio.gather(
                    wrc_ingestion_task(),
                    f1_ingestion_task()
                )
            except Exception as e:
                logger.error(f"An error occurred in the main ingestion loop: {e}")
                
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        logger.info("--- Ingestion Worker Shutting Down ---")
        overall_task.cancel()
        championship_task.cancel()
        await asyncio.gather(overall_task, championship_task, return_exceptions=True)
        await close_redis_connection()

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, stopping worker.")
