import fastf1
import asyncio
from datetime import date
from typing import List
from models.calendar import CalendarEvent
from api.utils import get_logo_path, get_country_iso_code # Fixed import
import logging
import os

# Configure fastf1 cache
cache_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".fastf1_cache"))
if not os.path.exists(cache_path):
    os.makedirs(cache_path)
fastf1.Cache.enable_cache(cache_path)

logger = logging.getLogger(__name__)

async def get_f1_calendar_events(year: int) -> List[CalendarEvent]:
    """
    Fetches the F1 event schedule for a given year, including the winner and their team.
    """
    logger.info(f"Fetching F1 calendar for year {year}...")
    
    try:
        loop = asyncio.get_running_loop()
        
        schedule = await loop.run_in_executor(
            None, lambda: fastf1.get_event_schedule(year, include_testing=False)
        )
        
        f1_events = []
        for index, event_row in schedule.iterrows():
            event_id = int(f"{year}{event_row['RoundNumber']}")
            
            start_date = event_row['EventDate'].date()
            finish_date = event_row['EventDate'].date()
            
            event = None
            try:
                event = fastf1.get_event(year, event_row['RoundNumber'])
                if hasattr(event, 'sessions') and event.sessions:
                    session_dates = [s.date.date() for s in event.iter_sessions() if s.date]
                    if session_dates:
                        start_date = min(session_dates)
                        finish_date = max(session_dates)
            except Exception as e:
                logger.debug(f"Could not fetch detailed session dates for F1 event {event_row['EventName']}: {e}")

            winner_name = None
            winner_logo_path = None # Changed variable name

            if finish_date < date.today() and event is not None:
                try:
                    race = await loop.run_in_executor(None, lambda: event.get_race())
                    if race:
                        await loop.run_in_executor(None, lambda: race.load(laps=False, telemetry=False, weather=False, messages=False))
                        results = race.results
                        
                        if results is not None and not results.empty:
                            winner = results.loc[results['Position'] == 1.0].iloc[0]
                            winner_name = winner['FullName']
                            team_name = winner['TeamName']
                            
                            # Get logo path directly from the TeamName using our utils function
                            winner_logo_path = get_logo_path(team_name) # Fixed function call
                            
                            if not winner_logo_path:
                                logger.warning(f"Could not map team name '{team_name}' to a logo.")

                except Exception as e:
                    logger.warning(f"Could not fetch F1 winner for event {event_row['EventName']}: {e}")

            country_iso_code = get_country_iso_code(event_row['Country'])
            country_image_url = f"https://flagcdn.com/w320/{country_iso_code.lower()}.png" if country_iso_code else None

            f1_events.append(
                CalendarEvent(
                    id=event_id,
                    name=event_row['EventName'],
                    category="F1",
                    country=event_row['Country'],
                    country_image_url=country_image_url,
                    start_date=start_date,
                    finish_date=finish_date,
                    current_leader=winner_name,
                    current_leader_logo_path=winner_logo_path, # Changed field name
                )
            )
        
        logger.info(f"Successfully fetched {len(f1_events)} F1 events for {year}.")
        return f1_events

    except Exception as e:
        logger.error(f"Error fetching F1 calendar for year {year}: {e}")
        return []
