from typing import List, Optional
import httpx
import logging
from datetime import datetime, date

from openwrc.clients.wrc_api_client import WrcApiClient
from models.event import Stage
from models.stage_times import StageStandings, DriverTime
from models.calendar import CalendarEvent
from models.overall_standings import OverallStandings, OverallDriverStanding
from models.championship_standings import ChampionshipStandings, ChampionshipDriverStanding
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
    # ... (implementation is the same)
    pass

async def fetch_wrc_event_stages(event_id: int) -> List[Stage]:
    """Fetches all stages for a given WRC event from the source."""
    # ... (implementation is the same)
    pass

async def fetch_wrc_stage_times(event_id: int, stage_id: int) -> Optional[StageStandings]:
    """Fetches the live or final times for a specific WRC stage from the source."""
    # ... (implementation is the same)
    pass

async def fetch_wrc_overall_standings(event_id: int) -> Optional[OverallStandings]:
    """Fetches the overall standings for a given WRC event."""
    # ... (implementation is the same)
    pass

async def fetch_wrc_championship_standings(year: int) -> Optional[ChampionshipStandings]:
    """Fetches the WRC championship standings for a given year."""
    try:
        async with WrcApiClient() as client:
            all_seasons = await client.get_seasons()
            season = next((s for s in all_seasons if s.year == year and "world rally championship" in s.name.lower()), None)
            if not season:
                return None

            championships = await client.get_season_championships(season.season_id)
            # Find the main "Drivers" championship
            driver_championship = next((c for c in championships if c.name == "Drivers"), None)
            if not driver_championship:
                return None

            standings_data = await client.get_championship_standings(driver_championship.id)
            if not standings_data:
                return None

            standings_list = []
            for item in standings_data.standings:
                standings_list.append(
                    ChampionshipDriverStanding(
                        position=item.position,
                        driver_name=f"{item.driver.first_name} {item.driver.last_name}",
                        team_name=None, # Not directly available in this endpoint
                        logo_path=get_logo_path(item.manufacturer.name) if item.manufacturer else None,
                        points=item.points,
                        wins=item.wins
                    )
                )
            
            return ChampionshipStandings(
                year=year,
                category="WRC",
                standings=standings_list
            )
    except Exception as e:
        logger.error(f"Error fetching WRC championship standings for year {year}: {e}")
        return None
