import fastf1
import asyncio
from datetime import date
from typing import List
from models.calendar import CalendarEvent
from models.event import Stage
from api.utils import get_logo_path, get_country_iso_code
import logging
import os
import pandas as pd

# Configure fastf1 cache
cache_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".fastf1_cache"))
if not os.path.exists(cache_path):
    os.makedirs(cache_path)
fastf1.Cache.enable_cache(cache_path)

# Increase the default timeout for network requests
fastf1.req.CACHE_TIMEOUT = 30 # seconds

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
            event_id = int(f"{year}{event_row['RoundNumber']:02d}")
            
            # --- Corrected Date Logic ---
            # Collect all valid session dates directly from the schedule row
            session_dates = []
            for i in range(1, 6):
                date_col = f'Session{i}Date'
                if date_col in event_row and pd.notnull(event_row[date_col]):
                    session_dates.append(event_row[date_col].date())
            
            if session_dates:
                start_date = min(session_dates)
                finish_date = max(session_dates)
            else:
                # Fallback to the main event date if no session dates are found
                start_date = event_row['EventDate'].date()
                finish_date = event_row['EventDate'].date()

            winner_name = None
            winner_logo_path = None

            if finish_date < date.today():
                try:
                    # We still need get_event() to load race results
                    event = await loop.run_in_executor(None, lambda: fastf1.get_event(year, event_row['RoundNumber']))
                    race = await loop.run_in_executor(None, lambda: event.get_race())
                    if race:
                        await loop.run_in_executor(None, lambda: race.load(laps=False, telemetry=False, weather=False, messages=False))
                        results = race.results
                        
                        if results is not None and not results.empty:
                            winner = results.loc[results['Position'] == 1.0].iloc[0]
                            winner_name = winner['FullName']
                            team_name = winner['TeamName']
                            winner_logo_path = get_logo_path(team_name)
                            
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
                    current_leader_logo_path=winner_logo_path,
                )
            )
        
        logger.info(f"Successfully fetched {len(f1_events)} F1 events for {year}.")
        return f1_events

    except Exception as e:
        logger.error(f"Error fetching F1 calendar for year {year}: {e}")
        return []

def format_timedelta_to_time(td) -> str:
    """Converts a pandas Timedelta to a formatted string (MM:SS.m)"""
    if pd.isnull(td):
        return None
    
    total_seconds = td.total_seconds()
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    tenths = int((total_seconds * 10) % 10)
    
    hours = int(minutes // 60)
    if hours > 0:
        minutes = minutes % 60
        return f"{hours}:{minutes:02d}:{seconds:02d}.{tenths}"
    else:
        return f"{minutes:02d}:{seconds:02d}.{tenths}"

async def get_f1_event_sessions(year: int, round_number: int) -> List[Stage]:
    """
    Fetches the sessions for a specific F1 event.
    """
    logger.info(f"Fetching F1 sessions for year {year}, round {round_number}...")
    stages = []
    
    try:
        loop = asyncio.get_running_loop()
        event = await loop.run_in_executor(None, lambda: fastf1.get_event(year, round_number))
        
        if not event:
            return []

        for i, session_obj in enumerate(event.iter_sessions(), start=1):
            session_name = session_obj.name
            start_time = session_obj.date
            
            distance = 0.0 
            
            now = pd.Timestamp.now(tz='UTC')
            if start_time > now:
                status = "Scheduled"
                is_live = False
            else:
                if (now - start_time).total_seconds() > 4 * 3600: # 4 hours
                    status = "Completed"
                    is_live = False
                else:
                    status = "Running"
                    is_live = True

            winner_name = None
            winner_logo_path = None
            winner_time = None

            if status == "Completed":
                try:
                    session_data = await loop.run_in_executor(
                        None, lambda: event.get_session(session_name)
                    )
                    
                    if session_data:
                        await loop.run_in_executor(None, lambda: session_data.load(laps=False, telemetry=False, weather=False, messages=False))
                        results = session_data.results
                        
                        if results is not None and not results.empty:
                            winner = results.loc[results['Position'] == 1.0].iloc[0]
                            winner_name = winner['FullName']
                            team_name = winner['TeamName']
                            winner_logo_path = get_logo_path(team_name)
                            
                            time_col = 'Time'
                            if session_name in ["Qualifying", "Sprint Shootout"]:
                                time_col = 'Q3' if 'Q3' in winner and pd.notnull(winner['Q3']) else 'Time'
                                
                            if time_col in winner and not pd.isnull(winner[time_col]):
                                winner_time = format_timedelta_to_time(winner[time_col])

                except Exception as e:
                    logger.debug(f"Could not fetch F1 winner for session {session_name}: {e}")

            stage_id = int(f"{year}{round_number:02d}{i}")

            stages.append(
                Stage(
                    id=stage_id,
                    name=session_name,
                    number=i,
                    distance=distance,
                    start_time=start_time,
                    status=status,
                    is_live=is_live,
                    winner_name=winner_name,
                    winner_logo_path=winner_logo_path,
                    winner_time=winner_time
                )
            )
            
        return stages

    except Exception as e:
        logger.error(f"Error fetching F1 sessions for year {year}, round {round_number}: {e}")
        return []
