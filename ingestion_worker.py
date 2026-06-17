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
from api.wrc_service import fetch_wrc_event_stages, fetch_wrc_stage_times, fetch_wrc_overall_standings, fetch_wrc_championship_standings, fetch_wrc_team_championship_standings
from api.openf1_client import get_f1_event_sessions, fetch_f1_overall_standings, fetch_f1_championship_standings, fetch_f1_team_championship_standings, OPENF1_API_URL
from models.stage_times import StageStandings, DriverTime
from models.overall_standings import OverallStandings
from api.utils import get_logo_path

POLL_INTERVAL_SECONDS = 15
OVERALL_POLL_INTERVAL_SECONDS = 60
CHAMPIONSHIP_POLL_INTERVAL_SECONDS = 3600 # 1 hour

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

async def championship_standings_ingestion_task():
    """Periodically fetches and caches the championship standings for the current year."""
    while True:
        logger.info("Running championship standings cache update...")
        try:
            current_year = datetime.now().year
            
            # --- WRC ---
            wrc_drivers = await fetch_wrc_championship_standings(current_year)
            if wrc_drivers:
                await set_cached_data(f"championship:drivers:wrc:{current_year}", wrc_drivers.model_dump(mode='json'), expiration_seconds=CHAMPIONSHIP_POLL_INTERVAL_SECONDS * 2)
            
            wrc_teams = await fetch_wrc_team_championship_standings(current_year)
            if wrc_teams:
                await set_cached_data(f"championship:teams:wrc:{current_year}", wrc_teams.model_dump(mode='json'), expiration_seconds=CHAMPIONSHIP_POLL_INTERVAL_SECONDS * 2)

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
    """
    Fetches the live timing for an F1 session.
    """
    position_response = await client.get(f"{OPENF1_API_URL}/position?session_key={session_key}")
    position_response.raise_for_status()
    position_data = position_response.json()
    
    if not position_data:
        return StageStandings(stage_id=session_key, event_id=meeting_key, category="F1", is_live=True, standings=[])
        
    latest_positions = {p['driver_number']: p for p in sorted(position_data, key=lambda x: x['date'])}
            
    drivers_response = await client.get(f"{OPENF1_API_URL}/drivers?session_key={session_key}")
    drivers_response.raise_for_status()
    drivers_data = {d['driver_number']: d for d in drivers_response.json()}
    
    standings = []
    for drv, pos_data in latest_positions.items():
        driver_info = drivers_data.get(drv, {})
        standings.append(
            DriverTime(
                entry_id=drv,
                driver_name=driver_info.get('full_name', f"Driver {drv}"),
                logo_path=get_logo_path(driver_info.get('team_name')),
                status="OnTrack",
                time=None,
                position=pos_data['position']
            )
        )
        
    standings.sort(key=lambda x: x.position or 99)
    
    return StageStandings(stage_id=session_key, event_id=meeting_key, category="F1", is_live=True, standings=standings)

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

async def main_loop():
    """The main loop of the ingestion worker."""
    logger.info("--- Ingestion Worker Starting ---")
    
    if not await check_redis_connection():
        logger.error("Could not connect to Redis. Aborting worker.")
        return

    # Start background tasks
    asyncio.create_task(overall_standings_ingestion_task())
    asyncio.create_task(championship_standings_ingestion_task())

    while True:
        try:
            await asyncio.gather(
                wrc_ingestion_task(),
                f1_ingestion_task()
            )
        except Exception as e:
            logger.error(f"An error occurred in the main loop: {e}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("--- Ingestion Worker Shutting Down ---")
        asyncio.run(close_redis_connection())
