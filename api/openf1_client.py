import asyncio
from typing import List, Optional, Tuple
import httpx
from datetime import datetime, date, timezone
import logging

from models.calendar import CalendarEvent
from models.event import Stage
from api.utils import get_logo_path, get_country_iso_code

OPENF1_API_URL = "https://api.openf1.org/v1"
logger = logging.getLogger(__name__)

def format_timedelta_to_time(seconds: float) -> str:
    """Converts seconds to a formatted string (MM:SS.m)"""
    if seconds is None:
        return None
    
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    tenths = int((seconds * 10) % 10)
    
    hours = int(minutes // 60)
    if hours > 0:
        minutes = minutes % 60
        return f"{hours}:{minutes:02d}:{remaining_seconds:02d}.{tenths}"
    else:
        return f"{minutes:02d}:{remaining_seconds:02d}.{tenths}"

async def get_race_winner_from_openf1(client: httpx.AsyncClient, session_key: int) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetches the winner of a race session using the OpenF1 API.
    It works by finding the driver in position 1 on the last lap.
    Returns a tuple of (winner_name, team_name).
    """
    retries = 3
    delay = 2  # seconds
    
    for i in range(retries):
        try:
            await asyncio.sleep(delay) # Delay before each attempt
            
            position_response = await client.get(
                f"{OPENF1_API_URL}/position?session_key={session_key}&position=1"
            )
            position_response.raise_for_status() # This will raise HTTPStatusError for 4xx/5xx responses
            position_data = position_response.json()
            
            if not position_data:
                logger.debug(f"No position data found for session {session_key}.")
                return None, None
                
            position_data.sort(key=lambda x: x['date'], reverse=True)
            final_p1_record = position_data[0]
            
            driver_number = final_p1_record['driver_number']
            
            driver_response = await client.get(
                f"{OPENF1_API_URL}/drivers?session_key={session_key}&driver_number={driver_number}"
            )
            driver_response.raise_for_status()
            driver_data = driver_response.json()
            
            if driver_data:
                driver = driver_data[0]
                winner_name = driver.get('full_name')
                team_name = driver.get('team_name')
                return winner_name, team_name
                
            return None, None

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and i < retries - 1:
                logger.warning(f"Rate limit hit (429) for session {session_key}. Retrying in {delay * (2**i)}s...")
                await asyncio.sleep(delay * (2**i)) # Exponential backoff
                continue
            elif e.response.status_code == 404:
                logger.warning(f"HTTP error fetching winner for session {session_key}: {e} (Data not found).")
                return None, None
            else:
                logger.error(f"HTTP error fetching winner for session {session_key}: {e}")
                return None, None
        except Exception as e:
            logger.error(f"An unexpected error occurred fetching winner for session {session_key}: {e}")
            return None, None
    
    logger.error(f"Failed to fetch winner for session {session_key} after {retries} retries.")
    return None, None

async def get_session_fastest_driver(client: httpx.AsyncClient, session_key: int) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Fetches the fastest driver for a practice or qualifying session.
    Queries the /laps endpoint to find the minimum lap_duration.
    """
    retries = 3
    delay = 1
    
    for i in range(retries):
        try:
            await asyncio.sleep(delay)
            laps_response = await client.get(f"{OPENF1_API_URL}/laps?session_key={session_key}")
            laps_response.raise_for_status()
            laps_data = laps_response.json()
            
            if not laps_data:
                return None, None, None
                
            # Find lap with min lap_duration
            valid_laps = [lap for lap in laps_data if lap.get('lap_duration') is not None]
            if not valid_laps:
                return None, None, None
                
            fastest_lap = min(valid_laps, key=lambda x: x['lap_duration'])
            driver_number = fastest_lap['driver_number']
            time_seconds = fastest_lap['lap_duration']
            
            driver_response = await client.get(
                f"{OPENF1_API_URL}/drivers?session_key={session_key}&driver_number={driver_number}"
            )
            driver_response.raise_for_status()
            driver_data = driver_response.json()
            
            if driver_data:
                driver = driver_data[0]
                winner_name = driver.get('full_name')
                team_name = driver.get('team_name')
                winner_time = format_timedelta_to_time(time_seconds)
                return winner_name, team_name, winner_time
                
            return None, None, None
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and i < retries - 1:
                await asyncio.sleep(delay * (2**i))
                continue
            return None, None, None
        except Exception:
            return None, None, None
            
    return None, None, None

async def get_openf1_calendar_events(year: int) -> List[CalendarEvent]:
    """
    Fetches the F1 event schedule for a given year using the OpenF1 API.
    """
    logger.info(f"Fetching F1 calendar for year {year} from OpenF1...")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            meetings_task = client.get(f"{OPENF1_API_URL}/meetings?year={year}")
            sessions_task = client.get(f"{OPENF1_API_URL}/sessions?year={year}")
            
            meetings_response, sessions_response = await asyncio.gather(meetings_task, sessions_task)
            
            meetings_data = meetings_response.json()
            sessions_data = sessions_response.json()

            if not isinstance(meetings_data, list) or not isinstance(sessions_data, list):
                logger.warning(f"OpenF1 API returned non-list data for year {year}. Assuming no events.")
                return []
            
            sessions_by_meeting = {}
            for session in sessions_data:
                key = session['meeting_key']
                if key not in sessions_by_meeting:
                    sessions_by_meeting[key] = []
                sessions_by_meeting[key].append(session)

            f1_events = []
            
            for meeting in meetings_data:
                meeting_key = meeting['meeting_key']
                
                if meeting_key not in sessions_by_meeting:
                    continue

                meeting_sessions = sessions_by_meeting[meeting_key]
                
                session_dates = [datetime.fromisoformat(s['date_start']).date() for s in meeting_sessions]
                start_date = min(session_dates)
                finish_date = max(session_dates)
                
                race_session = next((s for s in meeting_sessions if s['session_name'] == 'Race'), None)
                
                winner_name, team_name = None, None
                if finish_date < date.today() and race_session:
                    winner_name, team_name = await get_race_winner_from_openf1(client, race_session['session_key'])

                country_iso_code = get_country_iso_code(meeting['country_name'])
                country_image_url = f"https://flagcdn.com/w320/{country_iso_code.lower()}.png" if country_iso_code else None

                f1_events.append(
                    CalendarEvent(
                        id=meeting['meeting_key'],
                        name=meeting['meeting_name'],
                        category="F1",
                        country=meeting['country_name'],
                        country_image_url=country_image_url,
                        start_date=start_date,
                        finish_date=finish_date,
                        current_leader=winner_name,
                        current_leader_logo_path=get_logo_path(team_name) if team_name else None,
                    )
                )
        
        logger.info(f"Successfully fetched {len(f1_events)} F1 events from OpenF1 for {year}.")
        return f1_events

    except Exception as e:
        logger.error(f"An unexpected error occurred fetching F1 calendar for year {year}: {e}")
        return []

async def get_f1_event_sessions(meeting_key: int) -> List[Stage]:
    """
    Fetches the sessions for a specific F1 event using the OpenF1 API.
    """
    logger.info(f"Fetching F1 sessions for meeting_key {meeting_key}...")
    stages = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            sessions_response = await client.get(f"{OPENF1_API_URL}/sessions?meeting_key={meeting_key}")
            sessions_response.raise_for_status()
            sessions_data = sessions_response.json()

            # Sort sessions by date to get a logical order
            sessions_data.sort(key=lambda s: s['date_start'])

            for i, session in enumerate(sessions_data, start=1):
                start_time = datetime.fromisoformat(session['date_start'])
                end_time = datetime.fromisoformat(session['date_end'])
                
                # Determine status
                now = datetime.now(timezone.utc)
                if now > end_time:
                    status = "Completed"
                    is_live = False
                elif start_time <= now <= end_time:
                    status = "Running"
                    is_live = True
                else:
                    status = "Scheduled"
                    is_live = False

                winner_name = None
                winner_logo_path = None
                winner_time = None
                
                if status == "Completed":
                    session_name = session['session_name']
                    session_key = session['session_key']
                    
                    if session_name in ["Race", "Sprint"]:
                        # For races we get the actual winner
                        w_name, t_name = await get_race_winner_from_openf1(client, session_key)
                        winner_name = w_name
                        winner_logo_path = get_logo_path(t_name) if t_name else None
                    else:
                        # For practice/qualifying we get the fastest driver
                        w_name, t_name, w_time = await get_session_fastest_driver(client, session_key)
                        winner_name = w_name
                        winner_logo_path = get_logo_path(t_name) if t_name else None
                        winner_time = w_time

                stages.append(
                    Stage(
                        id=session['session_key'],
                        name=session['session_name'],
                        number=i,
                        distance=0.0, # Not available in OpenF1
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
        logger.error(f"Error fetching F1 sessions for meeting_key {meeting_key}: {e}")
        return []
