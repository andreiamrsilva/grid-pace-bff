import asyncio
import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)

from core.redis_service import set_cached_data
from core.database_service import get_all_events_from_db, get_last_archived_year, upsert_events
from ingestion.strategy import registry

# Ensure strategies are registered by importing clients
import ingestion.wrc_client
import ingestion.openf1_client

async def find_live_stages():
    """
    Scans the calendar from the DB to find events that are currently active.
    Then, fetches their stages using the appropriate Strategy to find which are 'Running'.
    """
    try:
        all_events = get_all_events_from_db()
        today = date.today()

        live_stages = []
        for event in all_events:
            if event.start_date <= today <= event.finish_date:
                try:
                    strategy = registry.get_strategy(event.category)
                    stages = await strategy.fetch_event_stages(event.id)
                    live_stages.extend([(event.id, s.id, event.category) for s in stages if s.is_live])
                except ValueError as e:
                    logger.warning(f"Strategy error for event {event.id}: {e}")
                except Exception as e:
                    logger.error(f"Error fetching stages for live event {event.id}: {e}")

        return live_stages
    except Exception as e:
        logger.error(f"Error finding live stages: {e}")
        return []

async def run_live_timing_ingestion():
    """Ingests live timing data for all active events across all sports."""
    live_stages = await find_live_stages()

    if not live_stages:
        return

    for event_id, stage_id, category in live_stages:
        try:
            strategy = registry.get_strategy(category)
            stage_standings = await strategy.fetch_live_timing(event_id, stage_id)
            if stage_standings:
                redis_key = f"live:times:{category.lower()}:{stage_id}"
                await set_cached_data(redis_key, stage_standings.model_dump(mode='json'), expiration_seconds=60)
        except Exception as e:
            logger.error(f"Error during {category} live ingestion for Stage {stage_id}: {e}")

async def run_overall_standings_ingestion():
    """Ingests overall standings once for running or recently completed events."""
    try:
        all_events = get_all_events_from_db()
        today = date.today()

        for event in all_events:
            if event.start_date <= today <= event.finish_date or (event.finish_date < today and (today - event.finish_date).days < 3):
                try:
                    strategy = registry.get_strategy(event.category)
                    overall = await strategy.fetch_overall_standings(event.id)
                    if overall:
                        redis_key = f"overall:standings:{event.category.lower()}:{event.id}"
                        await set_cached_data(redis_key, overall.model_dump(mode='json'), expiration_seconds=300)
                except Exception as e:
                    logger.error(f"Error fetching {event.category} overall standings for event {event.id}: {e}")
    except Exception as e:
        logger.error(f"Error finding events for overall standings ingestion: {e}")

async def run_championship_standings_ingestion():
    """Fetches and caches the championship standings for the current year for all sports."""
    logger.info("Running championship standings cache update for all sports...")
    current_year = datetime.now().year
    
    for category in registry.get_all_categories():
        try:
            strategy = registry.get_strategy(category)
            
            drivers = await strategy.fetch_driver_championship(current_year)
            if drivers:
                await set_cached_data(f"championship:drivers:{category.lower()}:{current_year}", drivers.model_dump(mode='json'), expiration_seconds=7200)

            teams = await strategy.fetch_team_championship(current_year)
            if teams:
                await set_cached_data(f"championship:teams:{category.lower()}:{current_year}", teams.model_dump(mode='json'), expiration_seconds=7200)
        except Exception as e:
            logger.error(f"Error updating championship standings cache for {category}: {e}")

async def run_historic_archive():
    """Archives past years for all registered sports."""
    logger.info("Running historic database archive for all sports...")
    try:
        last_archived_year = get_last_archived_year()
        current_year = datetime.now().year
        years_to_archive = list(range(last_archived_year + 1, current_year))
        
        if not years_to_archive:
            return
            
        all_events = []
        for category in registry.get_all_categories():
            try:
                strategy = registry.get_strategy(category)
                events = await strategy.fetch_calendar_events(years_to_archive)
                all_events.extend(events or [])
            except Exception as e:
                logger.error(f"Error archiving past years for {category}: {e}")
                
        await upsert_events(all_events)
    except Exception as e:
        logger.error(f"Error in historic archive orchestration: {e}")

async def run_current_year_update():
    """Updates the current year's events for all registered sports."""
    logger.info("Running update for current year events for all sports...")
    try:
        current_year = datetime.now().year
        all_events = []
        
        for category in registry.get_all_categories():
            try:
                strategy = registry.get_strategy(category)
                events = await strategy.fetch_calendar_events([current_year])
                all_events.extend(events or [])
            except Exception as e:
                logger.error(f"Error updating current year events for {category}: {e}")
                
        await upsert_events(all_events)
    except Exception as e:
        logger.error(f"Error in current year update orchestration: {e}")
