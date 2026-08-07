import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from core.config import settings
from core.utils import get_logo_path, get_country_iso_code
from models.calendar import CalendarEvent
from models.championship_standings import ChampionshipStandings, ChampionshipDriverStanding, ChampionshipTeamStandings, \
    ChampionshipTeamStanding
from models.event import Stage
from models.overall_standings import OverallStandings, OverallDriverStanding
from models.stage_times import StageStandings, DriverTime
from models.timeline import TimelineEvent, TimelineEventSource, TimelineEventSeverity

OPENF1_API_URL = settings.OPENF1_API_URL
ERGAST_API_URL = settings.ERGAST_API_URL
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

def is_retryable_exception(exception: BaseException) -> bool:
    import httpx
    if isinstance(exception, httpx.HTTPStatusError):
        if exception.response.status_code in (401, 403, 404):
            return False
    return True

def handle_openf1_exception(e: Exception, logger, context_msg: str):
    import httpx
    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 403):
        logger.warning(f"OpenF1 API access restricted ({e.response.status_code}) during live session. {context_msg}")
    else:
        logger.error(f"{context_msg}: {e}")

import time

class OpenF1AuthManager:
    def __init__(self):
        self._token: Optional[str] = None
        self._expires_at: float = 0
        self._lock = asyncio.Lock()

    async def get_token(self) -> Optional[str]:
        if not settings.OPENF1_USERNAME or not settings.OPENF1_PASSWORD:
            return None

        # Check if token is valid and not expiring within the next 60 seconds
        if self._token and time.time() < (self._expires_at - 60):
            return self._token

        async with self._lock:
            # Double check inside lock
            if self._token and time.time() < (self._expires_at - 60):
                return self._token

            try:
                token_url = "https://api.openf1.org/token"
                payload = {
                    "username": settings.OPENF1_USERNAME,
                    "password": settings.OPENF1_PASSWORD
                }
                headers = {
                    "Content-Type": "application/x-www-form-urlencoded"
                }
                async with httpx.AsyncClient() as client:
                    response = await client.post(token_url, data=payload, headers=headers, timeout=10.0)
                    response.raise_for_status()
                    token_data = response.json()
                    
                    self._token = token_data.get("access_token")
                    expires_in = int(token_data.get("expires_in", 3600))
                    self._expires_at = time.time() + expires_in
                    
                    logger.info("Successfully fetched new OpenF1 OAuth2 token.")
                    return self._token
            except Exception as e:
                logger.error(f"Failed to obtain OpenF1 token: {e}")
                return None

auth_manager = OpenF1AuthManager()

@retry(
    stop=stop_after_attempt(3), 
    wait=wait_exponential(multiplier=1, min=2, max=10), 
    reraise=True,
    retry=retry_if_exception(is_retryable_exception)
)
async def fetch_json_with_retry(client: httpx.AsyncClient, url: str, allow_404: bool = False) -> Any:
    """
    Helper to fetch JSON from an API with exponential backoff.
    Will retry up to 3 times on any exception except 401/403/404.
    If allow_404 is True, returns [] on HTTP 404.
    """
    logger.debug(f"Fetching URL (with retry): {url}")
    headers = {}
    if url.startswith(settings.OPENF1_API_URL):
        token = await auth_manager.get_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
            headers["accept"] = "application/json"

    try:
        response = await client.get(url, headers=headers)
        if allow_404 and response.status_code == 404:
            return []
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        if allow_404 and e.response.status_code == 404:
            return []
        raise

async def get_race_winner_from_openf1(client: httpx.AsyncClient, session_key: int) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Fetches the winner of a race session and their total race time using the OpenF1 API.
    """
    try:
        position_data = await fetch_json_with_retry(
            client, f"{OPENF1_API_URL}/position?session_key={session_key}&position=1"
        )
        
        if not position_data:
            return None, None, None
            
        position_data.sort(key=lambda x: x['date'], reverse=True)
        final_p1_record = position_data[0]
        
        driver_number = final_p1_record['driver_number']
        
        driver_data = await fetch_json_with_retry(
            client, f"{OPENF1_API_URL}/drivers?session_key={session_key}&driver_number={driver_number}"
        )
        
        winner_time = None
        laps_data = await fetch_json_with_retry(
            client, f"{OPENF1_API_URL}/laps?session_key={session_key}&driver_number={driver_number}"
        )
        if laps_data:
            valid_laps = [lap['lap_duration'] for lap in laps_data if lap.get('lap_duration') is not None]
            if valid_laps:
                winner_time = format_seconds_to_time(sum(valid_laps))

        if driver_data:
            driver = driver_data[0]
            return driver.get('full_name'), driver.get('team_name'), winner_time
            
        return None, None, None
    except Exception as e:
        logger.warning(f"Failed to fetch race winner for session {session_key}: {e}")
        return None, None, None

async def get_session_fastest_driver(client: httpx.AsyncClient, session_key: int) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Fetches the fastest driver for a practice or qualifying session.
    """
    try:
        laps_data = await fetch_json_with_retry(client, f"{OPENF1_API_URL}/laps?session_key={session_key}")
        
        if not laps_data:
            return None, None, None
            
        valid_laps = [lap for lap in laps_data if lap.get('lap_duration') is not None]
        if not valid_laps:
            return None, None, None
            
        fastest_lap = min(valid_laps, key=lambda x: x['lap_duration'])
        driver_number = fastest_lap['driver_number']
        time_seconds = fastest_lap['lap_duration']
        
        driver_data = await fetch_json_with_retry(
            client, f"{OPENF1_API_URL}/drivers?session_key={session_key}&driver_number={driver_number}"
        )
        
        if driver_data:
            driver = driver_data[0]
            return driver.get('full_name'), driver.get('team_name'), format_seconds_to_time(time_seconds)
            
        return None, None, None
    except Exception as e:
        logger.warning(f"Failed to fetch fastest driver for session {session_key}: {e}")
        return None, None, None

async def get_openf1_calendar_events(year: int) -> List[CalendarEvent]:
    """
    Fetches the F1 event schedule for a given year using the OpenF1 API.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            meetings_data = await fetch_json_with_retry(client, f"{OPENF1_API_URL}/meetings?year={year}")
            sessions_data = await fetch_json_with_retry(client, f"{OPENF1_API_URL}/sessions?year={year}")

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
                
                meeting_sessions.sort(key=lambda s: s['date_start'])
                first_session_start = datetime.fromisoformat(meeting_sessions[0]['date_start'])
                last_session_end = datetime.fromisoformat(meeting_sessions[-1]['date_end'])
                
                if first_session_start.tzinfo is None:
                    first_session_start = first_session_start.replace(tzinfo=timezone.utc)
                if last_session_end.tzinfo is None:
                    last_session_end = last_session_end.replace(tzinfo=timezone.utc)
                
                now = datetime.now(timezone.utc)
                if now > last_session_end:
                    event_status = "Completed"
                elif now >= first_session_start:
                    event_status = "Running"
                else:
                    event_status = "Future event"

                winner_name, team_name = None, None
                if event_status in ["Running", "Completed"] and race_session:
                    winner_name, team_name, _ = await get_race_winner_from_openf1(client, race_session['session_key'])

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
    except Exception as e:
        handle_openf1_exception(e, logger, f"Error fetching F1 calendar events for year {year}")
        return []

async def get_f1_event_sessions(meeting_key: int) -> List[Stage]:
    """
    Fetches the sessions for a specific F1 event using the OpenF1 API.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            sessions_data = await fetch_json_with_retry(client, f"{OPENF1_API_URL}/sessions?meeting_key={meeting_key}")
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
                        w_name, t_name, w_time = await get_race_winner_from_openf1(client, session_key)
                        winner_name, winner_logo_path, winner_time = w_name, get_logo_path(t_name) if t_name else None, w_time
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
    except Exception as e:
        handle_openf1_exception(e, logger, f"Error fetching F1 sessions for meeting {meeting_key}")
        return []

async def fetch_f1_session_times(session_key: int, meeting_key: int, session_name: str = "Unknown", is_live: bool = False) -> Optional[StageStandings]:
    """
    Fetches the classification for an F1 session.
    Fetches all drivers, positions, and laps in bulk to avoid rate limiting.
    """
    logger.info(f"Fetching final standings for F1 session {session_key} in bulk...")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # If session_name is "Unknown", resolve true session_name from OpenF1 API
            if session_name == "Unknown":
                try:
                    session_info = await fetch_json_with_retry(client, f"{OPENF1_API_URL}/sessions?session_key={session_key}")
                    if session_info and isinstance(session_info, list) and len(session_info) > 0:
                        session_name = session_info[0].get('session_name', 'Unknown')
                except Exception as err:
                    logger.warning(f"Could not resolve session_name for session {session_key}: {err}")
            # 1. Fetch drivers, positions, laps, and intervals sequentially (using allow_404=True for telemetry endpoints)
            try:
                drivers_data = await fetch_json_with_retry(client, f"{OPENF1_API_URL}/drivers?session_key={session_key}", allow_404=True)
                positions_data = await fetch_json_with_retry(client, f"{OPENF1_API_URL}/position?session_key={session_key}", allow_404=True)
                laps_data = await fetch_json_with_retry(client, f"{OPENF1_API_URL}/laps?session_key={session_key}", allow_404=True)
                intervals_data = await fetch_json_with_retry(client, f"{OPENF1_API_URL}/intervals?session_key={session_key}", allow_404=True)
            except Exception as res:
                logger.warning(f"Error in fetching session {session_key} data bulk tasks: {res}")
                return None
            
            if not drivers_data:
                logger.debug(f"No driver data found for session {session_key}")
                return None
                
            # 2. Group positions by driver_number
            first_positions = {}
            latest_positions = {}
            if positions_data:
                for p in sorted(positions_data, key=lambda x: x['date'], reverse=False):
                    d_num = p['driver_number']
                    if d_num not in first_positions:
                        first_positions[d_num] = p['position']
                    latest_positions[d_num] = p['position']
                
            # 3. Group laps by driver_number
            laps_by_driver = {}
            if laps_data:
                for lap in laps_data:
                    d_num = lap['driver_number']
                    if lap.get('lap_duration') is not None:
                        laps_by_driver.setdefault(d_num, []).append(lap['lap_duration'])

            # Fallback: if positions_data is 404/empty, infer positions from laps data
            if not latest_positions and laps_by_driver:
                if session_name in ["Race", "Sprint"]:
                    sorted_drivers = sorted(
                        laps_by_driver.keys(),
                        key=lambda d: (len(laps_by_driver[d]), -sum(laps_by_driver[d])),
                        reverse=True
                    )
                else:
                    sorted_drivers = sorted(
                        laps_by_driver.keys(),
                        key=lambda d: min(laps_by_driver[d]) if laps_by_driver[d] else 999999
                    )
                for idx, d_num in enumerate(sorted_drivers, start=1):
                    latest_positions[d_num] = idx

            # 4. Group latest intervals by driver_number
            latest_intervals = {}
            if intervals_data:
                for i in sorted(intervals_data, key=lambda x: x['date']):
                    latest_intervals[i['driver_number']] = i
                    
            # Find winner (P1) and winner's total race time from laps
            winner_number = None
            for d_num, pos in latest_positions.items():
                if pos == 1:
                    winner_number = d_num
                    break
            
            winner_laps = laps_by_driver.get(winner_number, []) if winner_number else []
            winner_total_seconds = sum(winner_laps) if winner_laps else None

            # 5. Construct standings
            temp_standings = []
            for driver_info in drivers_data:
                driver_number = driver_info['driver_number']
                final_pos = latest_positions.get(driver_number)
                initial_pos = first_positions.get(driver_number)
                
                pos_change = None
                if initial_pos is not None and final_pos is not None:
                    pos_change = initial_pos - final_pos
                
                driver_laps = laps_by_driver.get(driver_number, [])
                driver_interval = latest_intervals.get(driver_number, {})
                gap = driver_interval.get('gap_to_leader')

                driver_time_seconds = None
                driver_time_str = None
                diff_to_first_str = None

                if session_name in ["Race", "Sprint"]:
                    if final_pos == 1:
                        if winner_total_seconds:
                            driver_time_seconds = winner_total_seconds
                            driver_time_str = format_seconds_to_time(winner_total_seconds)
                        diff_to_first_str = None
                    else:
                        if isinstance(gap, (int, float)) and gap > 0:
                            diff_to_first_str = f"+{gap:.3f}s"
                            if winner_total_seconds:
                                driver_time_seconds = winner_total_seconds + gap
                                driver_time_str = format_seconds_to_time(driver_time_seconds)
                            else:
                                driver_time_str = diff_to_first_str
                        elif isinstance(gap, str):
                            diff_to_first_str = gap
                            driver_time_str = gap
                        else:
                            # Fallback if interval data is absent
                            if driver_laps and winner_total_seconds:
                                total_s = sum(driver_laps)
                                diff_s = total_s - winner_total_seconds
                                if diff_s > 0:
                                    diff_to_first_str = f"+{diff_s:.3f}s"
                                    driver_time_str = format_seconds_to_time(total_s)
                else:
                    # Practice / Qualifying: fastest single lap
                    if driver_laps:
                        driver_time_seconds = min(driver_laps)
                        driver_time_str = format_seconds_to_time(driver_time_seconds)

                if final_pos is not None or driver_time_seconds is not None:
                    temp_standings.append({
                        'entry_id': driver_number,
                        'driver_name': driver_info.get('full_name', f"Driver {driver_number}"),
                        'logo_path': get_logo_path(driver_info.get('team_name')),
                        'status': "Finished",
                        'time_seconds': driver_time_seconds,
                        'time_str': driver_time_str,
                        'diff_to_first': diff_to_first_str,
                        'position': final_pos,
                        'position_change': pos_change
                    })

            if not temp_standings:
                logger.warning(f"Failed to extract any valid standings for session {session_key}")
                return None

            # Sort temp_standings by position
            temp_standings.sort(key=lambda x: x['position'] or 999)

            # Compute practice / qualifying diffs relative to P1
            if session_name not in ["Race", "Sprint"] and temp_standings:
                p1_time = temp_standings[0]['time_seconds']
                if p1_time is not None:
                    for s in temp_standings:
                        if s['position'] != 1 and s['time_seconds'] is not None:
                            diff_s = s['time_seconds'] - p1_time
                            if diff_s > 0:
                                s['diff_to_first'] = f"+{diff_s:.3f}s"
            
            standings = [
                DriverTime(
                    entry_id=s['entry_id'],
                    driver_name=s['driver_name'],
                    logo_path=s['logo_path'],
                    status=s['status'],
                    time=s['time_str'],
                    diff_to_first=s['diff_to_first'],
                    position=s['position'],
                    position_change=s['position_change']
                )
                for s in temp_standings
            ]
            
            logger.info(f"Successfully fetched final standings for session {session_key}.")
            return StageStandings(
                stage_id=session_key,
                event_id=meeting_key,
                category="F1",
                is_live=is_live,
                last_updated=datetime.now(timezone.utc),
                standings=standings
            )
    except Exception as e:
        handle_openf1_exception(e, logger, f"Error fetching final times for F1 session {session_key}")
        return None

async def fetch_f1_overall_standings(meeting_key: int) -> Optional[OverallStandings]:
    """
    Fetches the overall standings for an F1 event.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            sessions_data = await fetch_json_with_retry(client, f"{OPENF1_API_URL}/sessions?meeting_key={meeting_key}")
            
            fallback_order = ["Race", "Sprint", "Sprint Qualifying", "Qualifying", "Practice 3", "Practice 2", "Practice 1"]
            final_standings = None
            
            for session_name in fallback_order:
                session = next((s for s in sessions_data if s['session_name'] == session_name), None)
                if session:
                    session_key = session['session_key']
                    standings = await fetch_f1_session_times(session_key, meeting_key, session_name)
                    if standings and standings.standings:
                        final_standings = standings
                        break
            
            if not final_standings:
                return OverallStandings(event_id=meeting_key, category="F1", standings=[])

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
        handle_openf1_exception(e, logger, f"Error fetching F1 overall standings for meeting {meeting_key}")
        return None

async def fetch_f1_championship_standings(year: int) -> Optional[ChampionshipStandings]:
    """
    Fetches the F1 driver championship standings for a given year from the Ergast API.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            data = await fetch_json_with_retry(client, f"{ERGAST_API_URL}/{year}/driverStandings.json")
            
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
        handle_openf1_exception(e, logger, f"Error fetching F1 championship standings for year {year}")
        return None

async def fetch_f1_team_championship_standings(year: int) -> Optional[ChampionshipTeamStandings]:
    """
    Fetches the F1 constructor championship standings for a given year from the Ergast API.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            data = await fetch_json_with_retry(client, f"{ERGAST_API_URL}/{year}/constructorStandings.json")
            
            standings_data = data.get('MRData', {}).get('StandingsTable', {}).get('StandingsLists', [])
            if not standings_data:
                return None
            
            constructor_standings = standings_data[0].get('ConstructorStandings', [])
            
            standings_list = []
            for item in constructor_standings:
                constructor = item.get('Constructor', {})
                
                standings_list.append(
                    ChampionshipTeamStanding(
                        position=int(item.get('position')),
                        team_name=constructor.get('name'),
                        logo_path=get_logo_path(constructor.get('name')),
                        points=float(item.get('points')),
                        wins=int(item.get('wins'))
                    )
                )
            
            return ChampionshipTeamStandings(
                year=year,
                category="F1",
                standings=standings_list
            )
    except Exception as e:
        handle_openf1_exception(e, logger, f"Error fetching F1 team championship standings for year {year}")
        return None

import re

def translate_f1_message_to_pt(msg: str, flag: str, category: str) -> str:
    """Translates common F1 race control messages to Portuguese."""
    if not msg:
        return ""
        
    original = msg.upper()
    translated = original
    
    # Common F1 phrases dictionary (ordered roughly by length to prevent partial matches)
    replacements = {
        r"NOTED - LEAVING THE TRACK AND GAINING AN ADVANTAGE": "ANOTADO - SAÍDA DE PISTA COM GANHO DE VANTAGEM",
        r"GREEN LIGHT - PIT EXIT OPEN": "LUZ VERDE - SAÍDA DAS BOXES ABERTA",
        r"WILL BE INVESTIGATED AFTER THE SPRINT": "SERÁ INVESTIGADO APÓS A SPRINT",
        r"WILL BE INVESTIGATED AFTER THE RACE": "SERÁ INVESTIGADO APÓS A CORRIDA",
        r"WILL BE INVESTIGATED AFTER THE SESSION": "SERÁ INVESTIGADO APÓS A SESSÃO",
        r"LAPPED CARS MAY NOW OVERTAKE": "CARROS RETARDATÁRIOS PODEM ULTRAPASSAR",
        r"DOUBLE YELLOW IN TRACK SECTOR": "DUPLA AMARELA NO SETOR",
        r"YELLOW IN TRACK SECTOR": "AMARELA NO SETOR",
        r"DEBRIS IN TRACK SECTOR": "DETRITOS NO SETOR DA PISTA",
        r"CLEAR IN TRACK SECTOR": "PISTA LIMPA NO SETOR",
        r"VIRTUAL SAFETY CAR ENDING": "FIM DO SAFETY CAR VIRTUAL",
        r"SAFETY CAR IN THIS LAP": "SAFETY CAR RECOLHE NESTA VOLTA",
        r"DELETED - TRACK LIMITS": "TEMPO APAGADO - LIMITES DE PISTA",
        r"NO FURTHER INVESTIGATION": "NENHUMA INVESTIGAÇÃO ADICIONAL",
        r"WAVED BLUE FLAG FOR": "BANDEIRA AZUL AGITADA PARA",
        r"MOVING UNDER BRAKING": "MUDANÇA DE DIREÇÃO NA TRAVAGEM",
        r"INCIDENT INVOLVING": "INCIDENTE ENVOLVENDO",
        r"TRACK SURFACE SLIPPERY": "PISTA ESCORREGADIA",
        r"CAUSING A COLLISION": "CAUSAR UMA COLISÃO",
        r"SAFETY CAR DEPLOYED": "SAFETY CAR ACIONADO",
        r"VIRTUAL SAFETY CAR": "SAFETY CAR VIRTUAL",
        r"BLACK AND WHITE FLAG": "BANDEIRA PRETA E BRANCA",
        r"WILL BE REINSTATED": "SERÁ RESTABELECIDO",
        r"TIME PENALTY FOR": "PENALIZAÇÃO DE TEMPO PARA",
        r"STOPPED ON TRACK": "PARADO NA PISTA",
        r"CHEQUERED FLAG": "BANDEIRA QUADRICULADA",
        r"OVERTAKE ENABLED": "OVERTAKE ATIVADO",
        r"OVERTAKE DISABLED": "OVERTAKE DESATIVADO",
        r"RISK OF RAIN FOR": "RISCO DE CHUVA PARA",
        r"PIT EXIT CLOSED": "SAÍDA DAS BOXES FECHADA",
        r"SESSION STARTED": "SESSÃO INICIADA",
        r"DEBRIS ON TRACK": "DETRITOS NA PISTA",
        r"PIT LANE CLOSED": "PIT LANE FECHADO",
        r"PIT LANE OPEN": "PIT LANE ABERTO",
        r"CLEAR IN TURN": "PISTA LIMPA NA CURVA",
        r"UNDER INVESTIGATION": "SOB INVESTIGAÇÃO",
        r"WILL BE INVESTIGATED": "SERÁ INVESTIGADO",
        r"DOUBLE YELLOW": "DUPLA AMARELA",
        r"DOUBLE YELLOG": "DUPLA AMARELA",
        r"DRS DISABLED": "DRS DESATIVADO",
        r"TRACK SECTOR": "SETOR",
        r"DRS ENABLED": "DRS ATIVADO",
        r"TIME PENALTY": "PENALIZAÇÃO DE TEMPO",
        r"AT CURVE": "NA CURVA",
        r"AT TURN": "NA CURVA",
        r"NOTED": "ANOTADO",
        r"TURN": "CURVA",
        r"CARS": "CARROS",
        r"LAP": "VOLTA",
        r"CAR": "CARRO"
    }
    
    for en, pt in replacements.items():
        translated = re.sub(rf"\b{en}\b", pt, translated)
        
    # Formatting specific flag/category prefixes if applicable
    prefix = ""
    if flag in ['YELLOW', 'DOUBLE YELLOW']:
        prefix = "Bandeira Amarela: "
    elif flag == 'RED' or category == 'RedFlag':
        prefix = "Bandeira Vermelha: "
    elif category == 'SafetyCar' and "SAFETY CAR" not in translated:
        prefix = "Carro de Segurança: "
        
    final_msg = f"{prefix}{translated}".strip()
    return final_msg.title()

async def fetch_f1_race_control_messages(session_key: int) -> List[TimelineEvent]:
    """
    Fetches race control messages for an F1 session and maps them to our TimelineEvent model.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            data = await fetch_json_with_retry(client, f"{OPENF1_API_URL}/race_control?session_key={session_key}")
            
            if not data:
                return []
                
            events = []
            for item in data:
                flag = item.get('flag', '')
                category = item.get('category', '')
                msg = item.get('message', '').title()
                
                # Determine severity
                severity = TimelineEventSeverity.INFO
                if flag in ['YELLOW', 'DOUBLE YELLOW'] or category == 'SafetyCar':
                    severity = TimelineEventSeverity.WARNING
                elif flag == 'RED' or category == 'RedFlag':
                    severity = TimelineEventSeverity.CRITICAL
                elif 'STOPPED' in msg.upper() or 'CRASH' in msg.upper():
                    severity = TimelineEventSeverity.CRITICAL

                d_num = item.get('driver_number')
                if d_num is not None:
                    d_num = str(d_num)

                # Ensure date is parsed and timezone aware
                dt = datetime.fromisoformat(item['date'])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                # Comprehensive Portuguese mapping for common F1 terminology
                pt_msg = translate_f1_message_to_pt(item.get('message', ''), flag, category)

                # Create deterministic ID to avoid duplicate notifications on polling
                deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"f1_{session_key}_{item['date']}_{msg}"))

                events.append(
                    TimelineEvent(
                        id=deterministic_id,
                        timestamp=dt,
                        source=TimelineEventSource.F1_RACE_CONTROL,
                        severity=severity,
                        message=msg,
                        driver_number=d_num,
                        metadata={
                            "flag": flag,
                            "lap_number": item.get('lap_number'),
                            "scope": item.get('scope'),
                            "category": category,
                            "message_en": msg,
                            "message_pt": pt_msg
                        }
                    )
                )
            
            # Sort by timestamp
            events.sort(key=lambda x: x.timestamp)
            
            # Fetch Twitter data for the duration of these events
            if events:
                try:
                    from ingestion.twitter_client import fetch_tweets_for_session
                    start_time = events[0].timestamp
                    end_time = events[-1].timestamp
                    tweets = await fetch_tweets_for_session(
                        start_time, end_time, "from:F1", TimelineEventSource.F1_SOCIAL_MEDIA, "@F1"
                    )
                    if tweets:
                        events.extend(tweets)
                        events.sort(key=lambda x: x.timestamp)
                except Exception as ex:
                    logger.warning(f"Could not fetch F1 tweets for session {session_key}: {ex}")
                    
            return events
            
    except Exception as e:
        handle_openf1_exception(e, logger, f"Error fetching F1 race control messages for session {session_key}")
        return []

from ingestion.strategy import SportIngestionStrategy, registry

class F1IngestionStrategy(SportIngestionStrategy):
    async def fetch_calendar_events(self, years: List[int]) -> List[CalendarEvent]:
        events = []
        for year in years:
            events.extend(await get_openf1_calendar_events(year))
        return events

    async def fetch_event_stages(self, event_id: int) -> List[Stage]:
        return await get_f1_event_sessions(event_id)

    async def fetch_live_timing(self, event_id: int, stage_id: int) -> Optional[StageStandings]:
        return await fetch_f1_session_times(stage_id, event_id, "Unknown", is_live=True)

    async def fetch_overall_standings(self, event_id: int) -> Optional[OverallStandings]:
        return await fetch_f1_overall_standings(event_id)

    async def fetch_driver_championship(self, year: int) -> Optional[ChampionshipStandings]:
        return await fetch_f1_championship_standings(year)

    async def fetch_team_championship(self, year: int) -> Optional[ChampionshipTeamStandings]:
        return await fetch_f1_team_championship_standings(year)

registry.register("f1", F1IngestionStrategy())
