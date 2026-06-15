import asyncio
import logging
import httpx
from datetime import datetime, date

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("IngestionWorker")

from api.redis_service import set_cached_data, check_redis_connection, close_redis_connection
from api.routers.events import _fetch_wrc_event_stages, get_wrc_stage_times
from api.openf1_client import get_openf1_calendar_events, get_f1_event_sessions, OPENF1_API_URL, format_timedelta_to_time
from api.utils import get_logo_path
from api.routers.calendar import fetch_wrc_events_for_years
from models.stage_times import StageStandings, DriverTime

# --- Configuration ---
POLL_INTERVAL_SECONDS = 15  # Fast loop for live times
STAGES_POLL_INTERVAL_SECONDS = 60 # Slower loop for updating the stage list

async def find_live_wrc_stages():
    """
    Scans the WRC calendar to find stages that are currently live.
    """
    try:
        current_year = datetime.now().year
        events = await fetch_wrc_events_for_years([current_year])
        
        today = date.today()
        active_event = next((e for e in events if e.start_date <= today <= e.finish_date), None)
        
        if not active_event:
            return []

        stages = await _fetch_wrc_event_stages(active_event.id)
        
        live_stages = [(active_event.id, s.id) for s in stages if s.status == "Running" or s.is_live]
        return live_stages
    except Exception as e:
        logger.error(f"Error finding live WRC stages: {e}")
        return []

async def wrc_ingestion_task():
    """The core task for ingesting WRC live timing data."""
    live_stages = await find_live_wrc_stages()
    
    if not live_stages:
        return

    for event_id, stage_id in live_stages:
        try:
            logger.info(f"Fetching live times for WRC Event {event_id}, Stage {stage_id}...")
            stage_standings = await get_wrc_stage_times(event_id, stage_id)
            
            if stage_standings:
                redis_key = f"live:times:wrc:{stage_id}"
                await set_cached_data(redis_key, stage_standings.model_dump(mode='json'), expiration_seconds=60)
                logger.debug(f"Successfully cached live times for WRC Stage {stage_id}.")
            
        except Exception as e:
            logger.error(f"Error during WRC ingestion for Stage {stage_id}: {e}")

async def find_live_f1_sessions():
    """
    Scans the F1 calendar to find sessions that are currently live.
    """
    try:
        current_year = datetime.now().year
        events = await get_openf1_calendar_events(current_year)
        
        today = date.today()
        active_event = next((e for e in events if e.start_date <= today <= e.finish_date), None)
        
        if not active_event:
            return []

        sessions = await get_f1_event_sessions(active_event.id)
        
        live_sessions = [(active_event.id, s.id) for s in sessions if s.status == "Running" or s.is_live]
        return live_sessions
    except Exception as e:
        logger.error(f"Error finding live F1 sessions: {e}")
        return []

async def get_f1_live_timing(client: httpx.AsyncClient, session_key: int, meeting_key: int) -> StageStandings:
    """
    Fetches the live timing for an F1 session.
    """
    try:
        # Fetch current positions
        position_response = await client.get(f"{OPENF1_API_URL}/position?session_key={session_key}")
        position_response.raise_for_status()
        position_data = position_response.json()
        
        if not position_data:
            return StageStandings(stage_id=session_key, event_id=meeting_key, category="F1", is_live=True, standings=[])
            
        # Get the latest position for each driver
        latest_positions = {}
        for p in position_data:
            drv = p['driver_number']
            if drv not in latest_positions or p['date'] > latest_positions[drv]['date']:
                latest_positions[drv] = p
                
        # Fetch driver details to get names and teams
        drivers_response = await client.get(f"{OPENF1_API_URL}/drivers?session_key={session_key}")
        drivers_response.raise_for_status()
        drivers_data = {d['driver_number']: d for d in drivers_response.json()}
        
        # We could also fetch /intervals or /laps for times, but /position is a good start for live tracking
        
        standings = []
        for drv, pos_data in latest_positions.items():
            driver_info = drivers_data.get(drv, {})
            name = driver_info.get('full_name', f"Driver {drv}")
            team = driver_info.get('team_name')
            
            standings.append(
                DriverTime(
                    entry_id=drv,
                    driver_name=name,
                    logo_path=get_logo_path(team) if team else None,
                    status="OnTrack",
                    time=None, # To get exact gap times we'd need to query /intervals
                    position=pos_data['position']
                )
            )
            
        standings.sort(key=lambda x: x.position if x.position else 99)
        
        return StageStandings(
            stage_id=session_key,
            event_id=meeting_key,
            category="F1",
            is_live=True,
            standings=standings
        )
        
    except Exception as e:
        logger.error(f"Error fetching live timing for F1 session {session_key}: {e}")
        return None

async def f1_ingestion_task():
    """The core task for ingesting F1 live timing data."""
    live_sessions = await find_live_f1_sessions()
    
    if not live_sessions:
        return

    async with httpx.AsyncClient(timeout=10.0) as client:
        for meeting_key, session_key in live_sessions:
            try:
                logger.info(f"Fetching live times for F1 Meeting {meeting_key}, Session {session_key}...")
                standings = await get_f1_live_timing(client, session_key, meeting_key)
                
                if standings:
                    redis_key = f"live:times:f1:{session_key}"
                    await set_cached_data(redis_key, standings.model_dump(mode='json'), expiration_seconds=60)
                    logger.debug(f"Successfully cached live times for F1 Session {session_key}.")
                
            except Exception as e:
                logger.error(f"Error during F1 ingestion for Session {session_key}: {e}")


async def cache_active_event_stages_task():
    """
    Periodically fetches and caches the list of stages/sessions 
    for currently active WRC and F1 events.
    """
    while True:
        logger.info("Running active event stages cache update...")
        try:
            current_year = datetime.now().year
            today = date.today()
            
            # --- WRC ---
            wrc_events = await fetch_wrc_events_for_years([current_year])
            active_wrc_event = next((e for e in wrc_events if e.start_date <= today <= e.finish_date), None)
            
            if active_wrc_event:
                logger.info(f"WRC Event {active_wrc_event.id} is active. Updating stages cache...")
                stages = await _fetch_wrc_event_stages(active_wrc_event.id)
                if stages:
                    redis_key = f"event:wrc:{active_wrc_event.id}:stages"
                    await set_cached_data(redis_key, [s.model_dump(mode='json') for s in stages], expiration_seconds=300)
            
            # --- F1 ---
            f1_events = await get_openf1_calendar_events(current_year)
            active_f1_event = next((e for e in f1_events if e.start_date <= today <= e.finish_date), None)
            
            if active_f1_event:
                logger.info(f"F1 Event {active_f1_event.id} is active. Updating sessions cache...")
                sessions = await get_f1_event_sessions(active_f1_event.id)
                if sessions:
                    redis_key = f"event:f1:{active_f1_event.id}:stages"
                    await set_cached_data(redis_key, [s.model_dump(mode='json') for s in sessions], expiration_seconds=300)

        except Exception as e:
            logger.error(f"Error updating active event stages cache: {e}")
            
        await asyncio.sleep(STAGES_POLL_INTERVAL_SECONDS)

async def main_loop():
    """The main loop of the ingestion worker."""
    logger.info("--- Ingestion Worker Starting ---")
    
    if not await check_redis_connection():
        logger.error("Could not connect to Redis. Aborting worker.")
        return

    # Start the slow loop task in the background
    asyncio.create_task(cache_active_event_stages_task())

    while True:
        try:
            # Run fast loop ingestion tasks
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
