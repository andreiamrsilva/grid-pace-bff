import asyncio
from typing import List, Optional, Tuple
import httpx
from datetime import datetime, date, timezone
import logging

from models.calendar import CalendarEvent
from models.event import Stage
from models.stage_times import StageStandings, DriverTime
from models.overall_standings import OverallStandings, OverallDriverStanding
from models.championship_standings import ChampionshipStandings, ChampionshipDriverStanding
from api.utils import get_logo_path, get_country_iso_code

OPENF1_API_URL = "https://api.openf1.org/v1"
ERGAST_API_URL = "https://ergast.com/api/f1"
logger = logging.getLogger(__name__)

def format_seconds_to_time(seconds: float) -> str:
    """Converts seconds to a formatted string (HHh MMm SS.ms) with units."""
    if seconds is None:
        return None
    
    total_milliseconds = int(seconds * 1000)
    
    hours = total_milliseconds // 3_600_000
    total_milliseconds %= 3_600_000
    minutes = total_milliseconds // 60_000
    total_milliseconds %= 60_000
    secs = total_milliseconds // 1_000
    milliseconds = total_milliseconds % 1_000
    
    time_str = ""
    if hours > 0:
        time_str += f"{hours}h "
    if minutes > 0 or hours > 0:
        time_str += f"{minutes:02d}m "
    time_str += f"{secs:02d}.{milliseconds:03d}s"
    
    return time_str.strip()

async def get_race_winner_from_openf1(client: httpx.AsyncClient, session_key: int) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetches the winner of a race session using the OpenF1 API.
    """
    retries = 3
    delay = 2
    
    for i in range(retries):
        try:
            await asyncio.sleep(delay)
            
            position_response = await client.get(
                f"{OPENF1_API_URL}/position?session_key={session_key}&position=1"
            )
            position_response.raise_for_status()
            position_data = position_response.json()
            
            if not position_data:
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
                return driver.get('full_name'), driver.get('team_name')
                
            return None, None

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and i < retries - 1:
                await asyncio.sleep(delay * (2**i))
                continue
            return None, None
        except Exception:
            return None, None
            
    return None, None

async def get_session_fastest_driver(client: httpx.AsyncClient, session_key: int) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Fetches the fastest driver for a practice or qualifying session.
    """
    try:
        await asyncio.sleep(1)
        laps_response = await client.get(f"{OPENF1_API_URL}/laps?session_key={session_key}")
        laps_response.raise_for_status()
        laps_data = laps_response.json()
        
        if not laps_data:
            return None, None, None
            
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
            return driver.get('full_name'), driver.get('team_name'), format_seconds_to_time(time_seconds)
            
        return None, None, None
    except Exception:
        return None, None, None

async def get_openf1_calendar_events(year: int) -> List[CalendarEvent]:
    """
    Fetches the F1 event schedule for a given year using the OpenF1 API.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            meetings_response = await client.get(f"{OPENF1_API_URL}/meetings?year={year}")
            sessions_response = await client.get(f"{OPENF1_API_URL}/sessions?year={year}")
            meetings_data = meetings_response.json()
            sessions_data = sessions_response.json()

            if not isinstance(meetings_data, list) or not isinstance(sessions_data, list):
                return []
            
            sessions_by_meeting = {m['meeting_key']: [] for m in meetings_data}
            for session in sessions_data:
                if session['meeting_key'] in sessions_by_meeting:
                    sessions_by_meeting[session['meeting_key']].append(session)

            f1_events = []
            for meeting in meetings_data:
                meeting_key = meeting['meeting_key']
                meeting_sessions = sessions_by_meeting.get(meeting_key, [])
                if not meeting_sessions:
                    continue

                session_dates = [datetime.fromisoformat(s['date_start']).date() for s in meeting_sessions]
                start_date, finish_date = min(session_dates), max(session_dates)
                
                race_session = next((s for s in meeting_sessions if s['session_name'] == 'Race'), None)
                
                # Determine Status
                today = date.today()
                event_status = "Future event"
                if today > finish_date:
                    event_status = "Completed"
                elif start_date <= today <= finish_date:
                    event_status = "Running"

                winner_name, team_name = None, None
                if event_status in ["Running", "Completed"] and race_session:
                    winner_name, team_name = await get_race_winner_from_openf1(client, race_session['session_key'])

                f1_events.append(
                    CalendarEvent(
                        id=meeting_key,
                        name=meeting['meeting_name'],
                        category="F1",
                        country=meeting['country_name'],
                        country_image_url=f"https://flagcdn.com/w320/{get_country_iso_code(meeting['country_name']).lower()}.png" if get_country_iso_code(meeting['country_name']) else None,
                        start_date=start_date,
                        finish_date=finish_date,
                        current_leader=winner_name,
                        current_leader_logo_path=get_logo_path(team_name) if team_name else None,
                        status=event_status
                    )
                )
        return f1_events
    except Exception:
        return []

async def get_f1_event_sessions(meeting_key: int) -> List[Stage]:
    """
    Fetches the sessions for a specific F1 event using the OpenF1 API.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            sessions_response = await client.get(f"{OPENF1_API_URL}/sessions?meeting_key={meeting_key}")
            sessions_data = sessions_response.json()
            sessions_data.sort(key=lambda s: s['date_start'])

            stages = []
            for i, session in enumerate(sessions_data, start=1):
                start_time = datetime.fromisoformat(session['date_start'])
                end_time = datetime.fromisoformat(session['date_end'])
                
                now = datetime.now(timezone.utc)
                status = "Scheduled"
                if now > end_time: status = "Completed"
                elif start_time <= now <= end_time: status = "Running"
                
                winner_name, winner_logo_path, winner_time = None, None, None
                if status == "Completed":
                    session_name = session['session_name']
                    session_key = session['session_key']
                    
                    if session_name in ["Race", "Sprint"]:
                        w_name, t_name = await get_race_winner_from_openf1(client, session_key)
                        winner_name, winner_logo_path = w_name, get_logo_path(t_name) if t_name else None
                    else:
                        w_name, t_name, w_time = await get_session_fastest_driver(client, session_key)
                        winner_name, winner_logo_path, winner_time = w_name, get_logo_path(t_name) if t_name else None, w_time

                stages.append(
                    Stage(
                        id=session['session_key'],
                        name=session['session_name'],
                        number=i,
                        distance=0.0,
                        start_time=start_time,
                        status=status,
                        is_live=(status == "Running"),
                        winner_name=winner_name,
                        winner_logo_path=winner_logo_path,
                        winner_time=winner_time
                    )
                )
            return stages
    except Exception:
        return []

async def fetch_f1_session_times(session_key: int, meeting_key: int, session_name: str = "Unknown") -> Optional[StageStandings]:
    """
    Fetches the final classification for a completed F1 session.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            drivers_response = await client.get(f"{OPENF1_API_URL}/drivers?session_key={session_key}")
            drivers_response.raise_for_status()
            drivers_data = {d['driver_number']: d for d in drivers_response.json()}
            
            if not drivers_data:
                return None

            standings = []
            
            if session_name in ["Race", "Sprint"]:
                pos_res = await client.get(f"{OPENF1_API_URL}/position?session_key={session_key}")
                pos_data = pos_res.json()
                if pos_data and isinstance(pos_data, list):
                    latest_positions = {p['driver_number']: p for p in sorted(pos_data, key=lambda x: x['date'])}
                    for drv_num, driver_info in drivers_data.items():
                        if drv_num in latest_positions:
                            final_pos = latest_positions[drv_num]['position']
                            standings.append(DriverTime(entry_id=drv_num, driver_name=driver_info.get('full_name', f"Driver {drv_num}"), logo_path=get_logo_path(driver_info.get('team_name')), status="Finished", time=None, position=final_pos))
            else:
                laps_res = await client.get(f"{OPENF1_API_URL}/laps?session_key={session_key}")
                laps_data = laps_res.json()
                if laps_data and isinstance(laps_data, list):
                    best_laps = {}
                    for lap in laps_data:
                        drv_num = lap.get('driver_number')
                        duration = lap.get('lap_duration')
                        if drv_num and duration:
                            if drv_num not in best_laps or duration < best_laps[drv_num]:
                                best_laps[drv_num] = duration
                    
                    sorted_drivers = sorted(best_laps.items(), key=lambda x: x[1])
                    for pos, (drv_num, duration) in enumerate(sorted_drivers, start=1):
                        driver_info = drivers_data.get(drv_num, {})
                        standings.append(DriverTime(entry_id=drv_num, driver_name=driver_info.get('full_name', f"Driver {drv_num}"), logo_path=get_logo_path(driver_info.get('team_name')), status="Finished", time=format_seconds_to_time(duration), position=pos))

            standings.sort(key=lambda x: x.position or 999)
            
            if not standings:
                return None

            return StageStandings(stage_id=session_key, event_id=meeting_key, category="F1", is_live=False, standings=standings)
    except Exception as e:
        logger.error(f"Error fetching final times for F1 session {session_key}: {e}")
        return None

async def fetch_f1_overall_standings(meeting_key: int) -> Optional[OverallStandings]:
    """
    Fetches the overall standings for an F1 event.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            sessions_response = await client.get(f"{OPENF1_API_URL}/sessions?meeting_key={meeting_key}")
            race_session = next((s for s in sessions_response.json() if s['session_name'] == 'Race'), None)
            if not race_session:
                return None
            
            session_key = race_session['session_key']
            
            final_standings = await fetch_f1_session_times(session_key, meeting_key, "Race")
            
            if not final_standings:
                return None

            overall_standings = [OverallDriverStanding(
                position=s.position,
                driver_name=s.driver_name,
                logo_path=s.logo_path,
                time=s.time,
                diff_to_first=s.diff_to_first,
                points=None # Points not available
            ) for s in final_standings.standings]
            
            return OverallStandings(event_id=meeting_key, category="F1", standings=overall_standings)
    except Exception as e:
        logger.error(f"Error fetching F1 overall standings for meeting {meeting_key}: {e}")
        return None

async def fetch_f1_championship_standings(year: int) -> Optional[ChampionshipStandings]:
    """
    Fetches the F1 driver championship standings for a given year from the Ergast API.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{ERGAST_API_URL}/{year}/driverStandings.json")
            response.raise_for_status()
            data = response.json()
            
            standings_data = data.get('MRData', {}).get('StandingsTable', {}).get('StandingsLists', [])
            if not standings_data:
                return None
            
            driver_standings = standings_data[0].get('DriverStandings', [])
            
            standings_list = []
            for item in driver_standings:
                driver = item.get('Driver', {})
                constructor = item.get('Constructors', [{}])[0]
                
                standings_list.append(
                    ChampionshipDriverStanding(
                        position=int(item.get('position')),
                        driver_name=f"{driver.get('givenName')} {driver.get('familyName')}",
                        team_name=constructor.get('name'),
                        logo_path=get_logo_path(constructor.get('name')),
                        points=float(item.get('points')),
                        wins=int(item.get('wins'))
                    )
                )
            
            return ChampionshipStandings(
                year=year,
                category="F1",
                standings=standings_list
            )
    except Exception as e:
        logger.error(f"Error fetching F1 championship standings for year {year}: {e}")
        return None
