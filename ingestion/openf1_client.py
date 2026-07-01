import asyncio
from typing import List, Optional, Tuple, Any
import httpx
from datetime import datetime, date, timezone
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from models.calendar import CalendarEvent
from models.event import Stage
from models.stage_times import StageStandings, DriverTime
from models.overall_standings import OverallStandings, OverallDriverStanding
from models.championship_standings import ChampionshipStandings, ChampionshipDriverStanding, ChampionshipTeamStandings, ChampionshipTeamStanding
from models.timeline import TimelineEvent, TimelineEventSource, TimelineEventSeverity
import uuid
from core.utils import get_logo_path, get_country_iso_code
from core.config import settings

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
        if exception.response.status_code in (401, 403):
            return False
    return True

def handle_openf1_exception(e: Exception, logger, context_msg: str):
    import httpx
    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 403):
        logger.warning(f"OpenF1 API access restricted ({e.response.status_code}) during live session. {context_msg}")
    else:
        logger.error(f"{context_msg}: {e}")

@retry(
    stop=stop_after_attempt(3), 
    wait=wait_exponential(multiplier=1, min=2, max=10), 
    reraise=True,
    retry=retry_if_exception(is_retryable_exception)
)
async def fetch_json_with_retry(client: httpx.AsyncClient, url: str) -> Any:
    """
    Helper to fetch JSON from an API with exponential backoff.
    Will retry up to 3 times on any exception (including HTTPStatusError) except 401/403.
    """
    logger.debug(f"Fetching URL (with retry): {url}")
    
    # Inject API key if configured and we are calling OpenF1
    if settings.OPENF1_API_KEY and url.startswith(settings.OPENF1_API_URL):
        if "?" in url:
            url += f"&api_key={settings.OPENF1_API_KEY}"
        else:
            url += f"?api_key={settings.OPENF1_API_KEY}"

    response = await client.get(url)
    response.raise_for_status()
    return response.json()

async def get_race_winner_from_openf1(client: httpx.AsyncClient, session_key: int) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetches the winner of a race session using the OpenF1 API.
    """
    try:
        position_data = await fetch_json_with_retry(
            client, f"{OPENF1_API_URL}/position?session_key={session_key}&position=1"
        )
        
        if not position_data:
            return None, None
            
        position_data.sort(key=lambda x: x['date'], reverse=True)
        final_p1_record = position_data[0]
        
        driver_number = final_p1_record['driver_number']
        
        driver_data = await fetch_json_with_retry(
            client, f"{OPENF1_API_URL}/drivers?session_key={session_key}&driver_number={driver_number}"
        )
        
        if driver_data:
            driver = driver_data[0]
            return driver.get('full_name'), driver.get('team_name')
            
        return None, None
    except Exception as e:
        logger.warning(f"Failed to fetch race winner for session {session_key}: {e}")
        return None, None

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
                
                # Determine Status
                now = datetime.now(timezone.utc)
                event_status = "Future event"
                is_completed = True
                is_running = False

                for session in meeting_sessions:
                    s_start = datetime.fromisoformat(session['date_start'])
                    if s_start.tzinfo is None:
                        s_start = s_start.replace(tzinfo=timezone.utc)
                    s_end = datetime.fromisoformat(session['date_end'])
                    if s_end.tzinfo is None:
                        s_end = s_end.replace(tzinfo=timezone.utc)
                        
                    if s_start <= now <= s_end:
                        is_running = True
                        is_completed = False
                        break
                    if now < s_start:
                        is_completed = False

                if is_running:
                    event_status = "Running"
                elif is_completed:
                    event_status = "Completed"
                else:
                    event_status = "Future event"

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
    except Exception as e:
        handle_openf1_exception(e, logger, f"Error fetching F1 sessions for meeting {meeting_key}")
        return []

async def fetch_f1_session_times(session_key: int, meeting_key: int, session_name: str = "Unknown") -> Optional[StageStandings]:
    """
    Fetches the final classification for a completed F1 session.
    Fetches all drivers, positions, and laps in bulk to avoid rate limiting.
    """
    logger.info(f"Fetching final standings for F1 session {session_key} in bulk...")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Fetch drivers, positions, and laps concurrently with tenacity
            drivers_task = fetch_json_with_retry(client, f"{OPENF1_API_URL}/drivers?session_key={session_key}")
            positions_task = fetch_json_with_retry(client, f"{OPENF1_API_URL}/position?session_key={session_key}")
            laps_task = fetch_json_with_retry(client, f"{OPENF1_API_URL}/laps?session_key={session_key}")
            
            # Using asyncio.gather with return_exceptions=True is safer so one failure doesn't crash everything
            # but since we want to fail gracefully if any important part fails, we just gather.
            results = await asyncio.gather(drivers_task, positions_task, laps_task, return_exceptions=True)
            
            for res in results:
                if isinstance(res, Exception):
                    logger.warning(f"Error in fetching session {session_key} data bulk tasks: {res}")
                    return None
                    
            drivers_data, positions_data, laps_data = results
            
            if not drivers_data:
                logger.warning(f"No driver data found for session {session_key}")
                return None
                
            # 2. Group positions by driver_number
            latest_positions = {}
            for p in sorted(positions_data, key=lambda x: x['date'], reverse=False):
                latest_positions[p['driver_number']] = p['position']
                
            # 3. Group laps by driver_number
            laps_by_driver = {}
            for lap in laps_data:
                d_num = lap['driver_number']
                if lap.get('lap_duration') is not None:
                    laps_by_driver.setdefault(d_num, []).append(lap['lap_duration'])
                    
            # 4. Construct standings
            temp_standings = []
            for driver_info in drivers_data:
                driver_number = driver_info['driver_number']
                final_pos = latest_positions.get(driver_number)
                
                driver_laps = laps_by_driver.get(driver_number, [])
                driver_time_seconds = None
                driver_time_str = None
                
                if driver_laps:
                    if session_name in ["Race", "Sprint"]:
                        driver_time_seconds = sum(driver_laps)
                    else:
                        driver_time_seconds = min(driver_laps)
                        
                    driver_time_str = format_seconds_to_time(driver_time_seconds)
                        
                # Only include drivers that participated (have a position or time)
                if final_pos is not None or driver_time_seconds is not None:
                    temp_standings.append({
                        'entry_id': driver_number,
                        'driver_name': driver_info.get('full_name', f"Driver {driver_number}"),
                        'logo_path': get_logo_path(driver_info.get('team_name')),
                        'status': "Finished",
                        'time_seconds': driver_time_seconds,
                        'time_str': driver_time_str,
                        'position': final_pos
                    })

            if not temp_standings:
                logger.warning(f"Failed to extract any valid standings for session {session_key}")
                return None

            # Sort temp_standings to find the first place
            temp_standings.sort(key=lambda x: x['position'] or 999)
            
            # Find the winning time (first valid time after sorting by position)
            winning_time_seconds = None
            for s in temp_standings:
                if s['time_seconds'] is not None:
                    winning_time_seconds = s['time_seconds']
                    break
            
            standings = []
            for s in temp_standings:
                diff_to_first_str = None
                if winning_time_seconds is not None and s['time_seconds'] is not None and s['time_seconds'] > winning_time_seconds:
                    diff_seconds = s['time_seconds'] - winning_time_seconds
                    diff_to_first_str = format_seconds_to_time(diff_seconds)
                    
                standings.append(
                    DriverTime(
                        entry_id=s['entry_id'],
                        driver_name=s['driver_name'],
                        logo_path=s['logo_path'],
                        status=s['status'],
                        time=s['time_str'],
                        diff_to_first=diff_to_first_str,
                        position=s['position']
                    )
                )
            
            logger.info(f"Successfully fetched final standings for session {session_key}.")
            return StageStandings(
                stage_id=session_key,
                event_id=meeting_key,
                category="F1",
                is_live=False,
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
            race_session = next((s for s in sessions_data if s['session_name'] == 'Race'), None)
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

                # Basic Portuguese mapping for common F1 flags/categories
                pt_msg = msg
                if flag == 'YELLOW' or flag == 'DOUBLE YELLOW':
                    pt_msg = f"Bandeira Amarela: {msg}"
                elif flag == 'RED' or category == 'RedFlag':
                    pt_msg = f"Bandeira Vermelha: {msg}"
                elif category == 'SafetyCar':
                    pt_msg = f"Carro de Segurança: {msg}"

                events.append(
                    TimelineEvent(
                        id=str(uuid.uuid4()),
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
        return await fetch_f1_session_times(stage_id, event_id, "Unknown")

    async def fetch_overall_standings(self, event_id: int) -> Optional[OverallStandings]:
        return await fetch_f1_overall_standings(event_id)

    async def fetch_driver_championship(self, year: int) -> Optional[ChampionshipStandings]:
        return await fetch_f1_championship_standings(year)

    async def fetch_team_championship(self, year: int) -> Optional[ChampionshipTeamStandings]:
        return await fetch_f1_team_championship_standings(year)

registry.register("f1", F1IngestionStrategy())
