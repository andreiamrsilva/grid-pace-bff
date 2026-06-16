from typing import List, Optional
import httpx
import logging
from datetime import datetime, date

from openwrc.clients.wrc_api_client import WrcApiClient
from models.event import Stage
from models.stage_times import StageStandings, DriverTime
from models.calendar import CalendarEvent
from models.overall_standings import OverallStandings, OverallDriverStanding
from api.utils import get_logo_path

logger = logging.getLogger(__name__)

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

async def fetch_wrc_events_for_years(years: List[int]) -> List[CalendarEvent]:
    """Fetches WRC events for a specific list of years, including leader details and status."""
    logger.info(f"Fetching WRC events for years: {years}...")
    wrc_events = []
    try:
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
    except Exception as e:
        logger.error(f"Error fetching WRC events: {e}")
    return wrc_events

async def fetch_wrc_event_stages(event_id: int) -> List[Stage]:
    """Fetches all stages for a given WRC event from the source."""
    try:
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
                        
                        winner_name, winner_logo_path, winner_time = None, None, None
                        if stage_details.status == "Completed":
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
                                
                        stages.append(Stage(id=stage_details.stage_id, name=stage_details.name, number=stage_details.number, distance=stage_details.distance, start_time=start_time, status=stage_details.status, is_live=stage_details.status == "Running", winner_name=winner_name, winner_logo_path=winner_logo_path, winner_time=winner_time))
            
            stages.sort(key=lambda s: s.number)
            return stages
    except Exception as e:
        logger.error(f"Error fetching WRC stages from source: {e}")
        return []

async def fetch_wrc_stage_times(event_id: int, stage_id: int) -> Optional[StageStandings]:
    """Fetches the live or final times for a specific WRC stage from the source."""
    logger.info(f"Fetching WRC stage times for event {event_id}, stage {stage_id}")
    try:
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

    except Exception as e:
        logger.error(f"Error fetching WRC stage times for stage {stage_id}: {e}")
        return None

async def fetch_wrc_overall_standings(event_id: int) -> Optional[OverallStandings]:
    """Fetches the overall standings for a given WRC event."""
    try:
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
                        points=None # WRC API might not have this easily available in this endpoint
                    ))

            return OverallStandings(
                event_id=event_id,
                category="WRC",
                standings=overall_standings
            )
    except Exception as e:
        logger.error(f"Error fetching WRC overall standings for event {event_id}: {e}")
        return None
