import asyncio
import logging
import httpx
from datetime import datetime, date

logger = logging.getLogger(__name__)

from api.redis_service import set_cached_data
from api.database_service import get_all_events_from_db, archive_past_years, update_current_year_events
from api.wrc_service import fetch_wrc_event_stages, fetch_wrc_stage_times, fetch_wrc_events_for_years
from api.openf1_client import get_f1_event_sessions, fetch_f1_championship_standings, fetch_f1_team_championship_standings
from models.stage_times import StageStandings
from models.overall_standings import OverallStandings

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

async def run_wrc_live_timing_ingestion():
    """Ingests WRC live timing data once."""
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

async def run_f1_live_timing_ingestion():
    """Ingests F1 live timing data once."""
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

async def run_overall_standings_ingestion():
    """Ingests overall standings once."""
    # ... (implementation is the same)
    pass

async def run_championship_standings_ingestion():
    """Fetches and caches the championship standings for the current year."""
    logger.info("Running championship standings cache update...")
    try:
        current_year = datetime.now().year
        # --- F1 ---
        f1_drivers = await fetch_f1_championship_standings(current_year)
        if f1_drivers:
            await set_cached_data(f"championship:drivers:f1:{current_year}", f1_drivers.model_dump(mode='json'), expiration_seconds=7200)

        f1_teams = await fetch_f1_team_championship_standings(current_year)
        if f1_teams:
            await set_cached_data(f"championship:teams:f1:{current_year}", f1_teams.model_dump(mode='json'), expiration_seconds=7200)
    except Exception as e:
        logger.error(f"Error updating championship standings cache: {e}")

async def run_historic_archive():
    """Archives past years."""
    logger.info("Running historic database archive...")
    try:
        await archive_past_years(fetch_wrc_events_for_years)
    except Exception as e:
        logger.error(f"Error in historic archive: {e}")

async def run_current_year_update():
    """Updates the current year's events."""
    logger.info("Running update for current year events...")
    try:
        await update_current_year_events(fetch_wrc_events_for_years)
    except Exception as e:
        logger.error(f"Error in current year update: {e}")
