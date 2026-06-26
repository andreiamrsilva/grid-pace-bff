from typing import List, Optional, Any
import httpx
import logging
from datetime import datetime, date, timezone, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential

from openwrc.clients.wrc_api_client import WrcApiClient
from models.event import Stage
from models.stage_times import StageStandings, DriverTime
from models.calendar import CalendarEvent
from models.overall_standings import OverallStandings, OverallDriverStanding
from models.championship_standings import ChampionshipStandings, ChampionshipDriverStanding, ChampionshipTeamStandings, ChampionshipTeamStanding
from core.utils import get_logo_path

logger = logging.getLogger(__name__)

WRC_API_URL = "https://p-p.redbull.com/rb-wrccom-lintegration-yv-prod/api"

def format_ms_to_time(ms: int) -> str:
    """Converts milliseconds to a formatted string with units (e.g., 1m 23.4s)."""
    if ms is None:
        return None
    
    prefix = ""
    if ms < 0:
        prefix = "+"
        ms = abs(ms)
        
    total_seconds = ms / 1000.0
    
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    tenths = int((total_seconds * 10) % 10)
    
    time_str = ""
    if hours > 0:
        time_str += f"{hours}h "
    if minutes > 0 or hours > 0:
        time_str += f"{minutes:02d}m "
    
    time_str += f"{prefix}{seconds:02d}.{tenths}s"
    
    return time_str.strip()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
async def fetch_json_with_retry(client: httpx.AsyncClient, url: str) -> Any:
    """Helper to fetch JSON from WRC API with exponential backoff."""
    response = await client.get(url)
    response.raise_for_status()
    return response.json()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
async def _fetch_wrc_events_for_years(years: List[int]) -> List[CalendarEvent]:
    logger.info(f"Fetching WRC events for years: {years}...")
    wrc_events = []
    async with WrcApiClient() as client:
        all_seasons = await client.get_seasons()
        seasons = [s for s in all_seasons if s.year in years and "world rally championship" in s.name.lower()]
        
        for season in seasons:
            season_detail = await client.get_season_detail(season.season_id)
            if not season_detail or not season_detail.season_rounds:
                continue
            
            for round_info in season_detail.season_rounds:
                if not round_info.event:
                    continue
                
                today = date.today()
                event_status = "Future event"
                if hasattr(round_info.event, 'status') and round_info.event.status == "Canceled":
                    event_status = "Canceled"
                elif today > round_info.event.finish_date:
                    event_status = "Completed"
                elif round_info.event.start_date <= today <= round_info.event.finish_date:
                    event_status = "Running"
                    try:
                        # Ensure we only show "Running" if there is an active stage right now
                        event_stages = await _fetch_wrc_event_stages(round_info.event.event_id)
                        if event_stages and not any(s.is_live for s in event_stages):
                            event_status = "Future event"
                    except Exception as e:
                        logger.warning(f"Failed to fetch stages to determine WRC live status for event {round_info.event.event_id}: {e}")

                current_leader, current_leader_logo_path = None, None
                if event_status in ["Running", "Completed"]:
                    try:
                        event_metadata = await client.get_event_metadata(round_info.event.event_id)
                        if event_metadata and event_metadata.rallies:
                            rally_id = event_metadata.rallies[0].rally_id
                            results = await client.get_rally_results(round_info.event.event_id, rally_id)
                            
                            if results:
                                leader_result = next((r for r in results if r.position == 1), None)
                                if leader_result:
                                    entries = await client.get_rally_entries(round_info.event.event_id, rally_id)
                                    leader_entry = next((e for e in entries if e.entry_id == leader_result.entry_id), None)
                                    if leader_entry:
                                        current_leader = leader_entry.driver.full_name
                                        if hasattr(leader_entry, 'manufacturer') and leader_entry.manufacturer:
                                            current_leader_logo_path = get_logo_path(leader_entry.manufacturer.name)
                    except Exception as e:
                        logger.warning(f"Could not fetch WRC leader for event {round_info.event.event_id}: {e}")

                country_name = round_info.event.country.name if hasattr(round_info.event, 'country') else "Unknown"
                iso2 = round_info.event.country.iso2.lower() if hasattr(round_info.event, 'country') and hasattr(round_info.event.country, 'iso2') else None
                
                wrc_events.append(
                    CalendarEvent(
                        id=round_info.event.event_id,
                        name=round_info.event.name,
                        category="WRC",
                        country=country_name,
                        country_image_url=f"https://flagcdn.com/w320/{iso2}.png" if iso2 else None,
                        start_date=round_info.event.start_date,
                        finish_date=round_info.event.finish_date,
                        current_leader=current_leader,
                        current_leader_logo_path=current_leader_logo_path,
                        status=event_status
                    )
                )
    return wrc_events

async def fetch_wrc_events_for_years(years: List[int]) -> List[CalendarEvent]:
    try:
        return await _fetch_wrc_events_for_years(years)
    except Exception as e:
        logger.error(f"Error fetching WRC events after retries: {e}")
        return []


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
async def _fetch_wrc_event_stages(event_id: int) -> List[Stage]:
    async with WrcApiClient() as client:
        event_metadata = await client.get_event_metadata(event_id)
        if not event_metadata or not event_metadata.rallies:
            return []

        main_rally = event_metadata.rallies[0]
        itinerary = await client.get_event_itineraries(event_id, main_rally.itinerary_id)
        if not itinerary or not itinerary.itinerary_legs:
            return []

        entries = await client.get_rally_entries(event_id, main_rally.rally_id)
        entries_dict = {entry.entry_id: entry for entry in entries}

        stages = []
        for leg in itinerary.itinerary_legs:
            for section in leg.itinerary_sections:
                for stage_details in section.stages:
                    start_time = next((c.first_car_due_date_time for c in section.controls if c.type == "StageStart" and c.stage_id == stage_details.stage_id), None)
                    
                    # Fix API bug where old stages are returned as 'Running'
                    actual_status = stage_details.status
                    if actual_status == "Running" and start_time:
                        now = datetime.now(timezone.utc)
                        if (now - start_time) > timedelta(hours=4):
                            actual_status = "Completed"
                            
                    winner_name, winner_logo_path, winner_time = None, None, None
                    if actual_status == "Completed":
                        try:
                            stage_results = await client.get_event_stage_results(event_id, stage_details.stage_id, main_rally.rally_id)
                            if stage_results:
                                winner_result = next((r for r in stage_results if r.position == 1), None)
                                if winner_result and winner_result.entry_id in entries_dict:
                                    winner_entry = entries_dict[winner_result.entry_id]
                                    winner_name = winner_entry.driver.full_name
                                    if hasattr(winner_entry, 'manufacturer') and winner_entry.manufacturer:
                                        winner_logo_path = get_logo_path(winner_entry.manufacturer.name)
                                    winner_time = format_ms_to_time(winner_result.stage_time_ms)
                        except Exception:
                            pass
                            
                    stages.append(Stage(id=stage_details.stage_id, name=stage_details.name, number=stage_details.number, distance=stage_details.distance, start_time=start_time, status=actual_status, is_live=actual_status == "Running", winner_name=winner_name, winner_logo_path=winner_logo_path, winner_time=winner_time))
        
        stages.sort(key=lambda s: s.number)
        return stages

async def fetch_wrc_event_stages(event_id: int) -> List[Stage]:
    try:
        return await _fetch_wrc_event_stages(event_id)
    except Exception as e:
        logger.error(f"Error fetching WRC stages from source after retries: {e}")
        return []


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
async def _fetch_wrc_stage_times(event_id: int, stage_id: int) -> Optional[StageStandings]:
    logger.info(f"Fetching WRC stage times for event {event_id}, stage {stage_id}")
    async with WrcApiClient() as client:
        event_metadata = await client.get_event_metadata(event_id)
        if not event_metadata or not event_metadata.rallies:
            logger.warning(f"No metadata or rallies found for event {event_id}")
            return None
        rally_id = event_metadata.rallies[0].rally_id

        entries_dict = {}
        entries = await client.get_rally_entries(event_id, rally_id)
        for entry in entries:
            entries_dict[entry.entry_id] = entry

        finished_drivers = []
        finished_entry_ids = set()
        try:
            stage_results = await client.get_event_stage_results(event_id, stage_id, rally_id)
            if not stage_results:
                logger.debug(f"No final results found for stage {stage_id}")
            else:
                stage_results.sort(key=lambda x: x.position if x.position else 999)
                for result in stage_results:
                    if result.entry_id in entries_dict:
                        entry = entries_dict[result.entry_id]
                        logo_path = get_logo_path(entry.manufacturer.name) if hasattr(entry, 'manufacturer') and entry.manufacturer else None
                        finished_drivers.append(DriverTime(entry_id=result.entry_id, driver_name=entry.driver.full_name, logo_path=logo_path, status="Finished", time=format_ms_to_time(result.stage_time_ms), diff_to_first=format_ms_to_time(result.diff_first_ms) if result.diff_first_ms else None, position=result.position))
                        finished_entry_ids.add(result.entry_id)
        except Exception as e:
            logger.warning(f"Could not fetch final results for stage {stage_id}: {e}")

        on_track_drivers = []
        try:
            split_results = await client.get_rally_stage_split_time_results(event_id, rally_id, stage_id)
            if not split_results:
                logger.debug(f"No split times found for stage {stage_id}")
            else:
                entry_splits = {}
                for split in split_results:
                    if split.entry_id not in entry_splits:
                        entry_splits[split.entry_id] = []
                    entry_splits[split.entry_id].append(split)
                
                for e_id, splits in entry_splits.items():
                    if e_id in finished_entry_ids:
                        continue
                    if e_id in entries_dict:
                        entry = entries_dict[e_id]
                        logo_path = get_logo_path(entry.manufacturer.name) if hasattr(entry, 'manufacturer') and entry.manufacturer else None
                        splits.sort(key=lambda x: x.elapsed_duration_ms, reverse=True)
                        latest_split = splits[0]
                        on_track_drivers.append(DriverTime(entry_id=e_id, driver_name=entry.driver.full_name, logo_path=logo_path, status="OnTrack", time=format_ms_to_time(latest_split.elapsed_duration_ms), last_split_id=latest_split.split_point_id))
        except Exception as e:
            logger.warning(f"Could not fetch split times for stage {stage_id}: {e}")

        on_track_drivers.sort(key=lambda x: x.last_split_id if x.last_split_id else 0, reverse=True)
        
        all_standings = finished_drivers + on_track_drivers
        if not all_standings:
            logger.warning(f"No standings could be generated for WRC stage {stage_id}")
            return None

        is_live = len(on_track_drivers) > 0

        return StageStandings(
            stage_id=stage_id,
            event_id=event_id,
            category="WRC",
            is_live=is_live,
            standings=all_standings
        )

async def fetch_wrc_stage_times(event_id: int, stage_id: int) -> Optional[StageStandings]:
    try:
        return await _fetch_wrc_stage_times(event_id, stage_id)
    except Exception as e:
        logger.error(f"Error fetching WRC stage times for stage {stage_id} after retries: {e}")
        return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
async def _fetch_wrc_overall_standings(event_id: int) -> Optional[OverallStandings]:
    async with WrcApiClient() as client:
        event_metadata = await client.get_event_metadata(event_id)
        if not event_metadata or not event_metadata.rallies:
            return None
        rally_id = event_metadata.rallies[0].rally_id

        entries_dict = {}
        entries = await client.get_rally_entries(event_id, rally_id)
        for entry in entries:
            entries_dict[entry.entry_id] = entry

        results = await client.get_rally_results(event_id, rally_id)
        if not results:
            # Fallback to the overall standings of the latest completed stage for ongoing rallies
            itinerary_id = event_metadata.rallies[0].itinerary_id
            itinerary = await client.get_event_itineraries(event_id, itinerary_id)
            if itinerary and itinerary.itinerary_legs:
                latest_stage_id = None
                for leg in itinerary.itinerary_legs:
                    for section in leg.itinerary_sections:
                        for stage in section.stages:
                            if stage.status == "Completed":
                                latest_stage_id = stage.stage_id
                
                if latest_stage_id:
                    results = await client.get_event_stage_results(event_id, latest_stage_id, rally_id)

        if not results:
            return None

        results.sort(key=lambda x: x.position if x.position else 999)
        
        overall_standings = []
        for result in results:
            if result.entry_id in entries_dict:
                entry = entries_dict[result.entry_id]
                logo_path = get_logo_path(entry.manufacturer.name) if hasattr(entry, 'manufacturer') and entry.manufacturer else None
                
                overall_standings.append(OverallDriverStanding(
                    position=result.position,
                    driver_name=entry.driver.full_name,
                    logo_path=logo_path,
                    time=format_ms_to_time(result.total_time_ms) if hasattr(result, 'total_time_ms') else None,
                    diff_to_first=format_ms_to_time(result.diff_first_ms) if hasattr(result, 'diff_first_ms') else None,
                    points=None
                ))

        return OverallStandings(
            event_id=event_id,
            category="WRC",
            standings=overall_standings
        )

async def fetch_wrc_overall_standings(event_id: int) -> Optional[OverallStandings]:
    try:
        return await _fetch_wrc_overall_standings(event_id)
    except Exception as e:
        logger.error(f"Error fetching WRC overall standings for event {event_id} after retries: {e}")
        return None

async def fetch_wrc_championship_standings(year: int) -> Optional[ChampionshipStandings]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            seasons_data = await fetch_json_with_retry(client, f"{WRC_API_URL}/seasons.json")
            season = next((s for s in seasons_data if s['year'] == year and "world rally championship" in s['name'].lower()), None)
            if not season: return None
            season_id = season['seasonId']

            season_detail_data = await fetch_json_with_retry(client, f"{WRC_API_URL}/season-detail.json?seasonId={season_id}")
            driver_championship = next((c for c in season_detail_data.get('championships', []) if c['type'] == "Drivers"), None)
            if not driver_championship: return None
            championship_id = driver_championship['championshipId']

            champ_detail_data = await fetch_json_with_retry(client, f"{WRC_API_URL}/championship-detail.json?championshipId={championship_id}&seasonId={season_id}")
            entry_map = {entry['championshipEntryId']: entry for entry in champ_detail_data.get('championshipEntries', [])}

            results_data = await fetch_json_with_retry(client, f"{WRC_API_URL}/championship-overall-results.json?championshipId={championship_id}&seasonId={season_id}")

            standings_list = []
            for item in results_data.get('entryResults', []):
                entry_id = item['championshipEntryId']
                if entry_id in entry_map:
                    driver_info = entry_map[entry_id]
                    driver_name = f"{driver_info['fieldOne']} {driver_info['fieldTwo']}"
                    team_name = driver_info.get('fieldFour')
                    
                    standings_list.append(
                        ChampionshipDriverStanding(
                            position=item.get('overallPosition'),
                            driver_name=driver_name,
                            team_name=team_name.title() if team_name else None,
                            logo_path=get_logo_path(team_name),
                            points=item.get('overallPoints'),
                            wins=None
                        )
                    )
            
            return ChampionshipStandings(year=year, category="WRC", standings=standings_list)
            
    except Exception as e:
        logger.error(f"Error fetching WRC championship standings for year {year} after retries: {e}")
        return None

async def fetch_wrc_team_championship_standings(year: int) -> Optional[ChampionshipTeamStandings]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            seasons_data = await fetch_json_with_retry(client, f"{WRC_API_URL}/seasons.json")
            season = next((s for s in seasons_data if s['year'] == year and "world rally championship" in s['name'].lower()), None)
            if not season: return None
            season_id = season['seasonId']

            season_detail_data = await fetch_json_with_retry(client, f"{WRC_API_URL}/season-detail.json?seasonId={season_id}")
            team_championship = next((c for c in season_detail_data.get('championships', []) if c['type'] == "Manufacturer"), None)
            if not team_championship: return None
            championship_id = team_championship['championshipId']

            results_data = await fetch_json_with_retry(client, f"{WRC_API_URL}/championship-overall-results.json?championshipId={championship_id}&seasonId={season_id}")

            champ_detail_data = await fetch_json_with_retry(client, f"{WRC_API_URL}/championship-detail.json?championshipId={championship_id}&seasonId={season_id}")
            entry_map = {entry['championshipEntryId']: entry for entry in champ_detail_data.get('championshipEntries', [])}

            standings_list = []
            for item in results_data.get('entryResults', []):
                entry_id = item['championshipEntryId']
                if entry_id in entry_map:
                    team_info = entry_map[entry_id]
                    team_name = team_info.get('fieldOne')
                    
                    standings_list.append(
                        ChampionshipTeamStanding(
                            position=item.get('overallPosition'),
                            team_name=team_name.title() if team_name else None,
                            logo_path=get_logo_path(team_name),
                            points=item.get('overallPoints'),
                            wins=None
                        )
                    )
            
            return ChampionshipTeamStandings(year=year, category="WRC", standings=standings_list)
            
    except Exception as e:
        logger.error(f"Error fetching WRC team championship standings for year {year} after retries: {e}")
        return None


from ingestion.strategy import SportIngestionStrategy, registry

class WrcIngestionStrategy(SportIngestionStrategy):
    async def fetch_calendar_events(self, years: List[int]) -> List[CalendarEvent]:
        return await fetch_wrc_events_for_years(years)

    async def fetch_event_stages(self, event_id: int) -> List[Stage]:
        return await fetch_wrc_event_stages(event_id)

    async def fetch_live_timing(self, event_id: int, stage_id: int) -> Optional[StageStandings]:
        return await fetch_wrc_stage_times(event_id, stage_id)

    async def fetch_overall_standings(self, event_id: int) -> Optional[OverallStandings]:
        return await fetch_wrc_overall_standings(event_id)

    async def fetch_driver_championship(self, year: int) -> Optional[ChampionshipStandings]:
        return await fetch_wrc_championship_standings(year)

    async def fetch_team_championship(self, year: int) -> Optional[ChampionshipTeamStandings]:
        return await fetch_wrc_team_championship_standings(year)

registry.register("wrc", WrcIngestionStrategy())
