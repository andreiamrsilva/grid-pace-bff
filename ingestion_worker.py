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

from api.redis_service import get_cached_data, set_cached_data, check_redis_connection, close_redis_connection
from api.database_service import get_all_events_from_db
from api.wrc_service import fetch_wrc_event_stages, fetch_wrc_stage_times, fetch_wrc_overall_standings
from api.openf1_client import get_f1_event_sessions, fetch_f1_overall_standings, OPENF1_API_URL
from models.stage_times import StageStandings, DriverTime
from models.overall_standings import OverallStandings
from api.utils import get_logo_path

POLL_INTERVAL_SECONDS = 15
OVERALL_POLL_INTERVAL_SECONDS = 60

def calculate_position_changes(old_standings: dict, new_standings: OverallStandings) -> OverallStandings:
    """
    Compares the new standings with the old ones from Redis and calculates the position_change.
    """
    if not old_standings or not old_standings.get('standings'):
        return new_standings

    old_positions = {driver['driver_name']: driver.get('position') for driver in old_standings['standings'] if driver.get('position') is not None}

    for driver in new_standings.standings:
        if driver.position is not None and driver.driver_name in old_positions:
            old_pos = old_positions[driver.driver_name]
            driver.position_change = old_pos - driver.position
        else:
            driver.position_change = 0

    return new_standings

async def find_active_events(category: str):
    """Scans the calendar from the DB to find events that are currently active."""
    try:
        all_events = get_all_events_from_db()
        today = date.today()
        return [e for e in all_events if e.category.lower() == category and e.start_date <= today <= e.finish_date]
    except Exception as e:
        logger.error(f"Error finding active {category} events: {e}")
        return []

async def overall_standings_ingestion_task():
    """Periodically fetches and caches the overall standings for active events."""
    while True:
        logger.info("Running overall standings cache update...")
        try:
            # --- WRC ---
            active_wrc_events = await find_active_events('wrc')
            for event in active_wrc_events:
                standings = await fetch_wrc_overall_standings(event.id)
                if standings:
                    redis_key = f"overall:wrc:{event.id}"
                    old_standings = await get_cached_data(redis_key)
                    standings = calculate_position_changes(old_standings, standings)
                    await set_cached_data(redis_key, standings.model_dump(mode='json'), expiration_seconds=300)
            
            # --- F1 ---
            active_f1_events = await find_active_events('f1')
            for event in active_f1_events:
                standings = await fetch_f1_overall_standings(event.id)
                if standings:
                    redis_key = f"overall:f1:{event.id}"
                    old_standings = await get_cached_data(redis_key)
                    standings = calculate_position_changes(old_standings, standings)
                    await set_cached_data(redis_key, standings.model_dump(mode='json'), expiration_seconds=300)

        except Exception as e:
            logger.error(f"Error updating overall standings cache: {e}")
            
        await asyncio.sleep(OVERALL_POLL_INTERVAL_SECONDS)

# ... (rest of the worker file remains the same)
async def main_loop():
    logger.info("--- Ingestion Worker Starting ---")
    if not await check_redis_connection():
        logger.error("Could not connect to Redis. Aborting worker.")
        return

    asyncio.create_task(overall_standings_ingestion_task())

    while True:
        # ... (wrc_ingestion_task and f1_ingestion_task for live stage times)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("--- Ingestion Worker Shutting Down ---")
        asyncio.run(close_redis_connection())
