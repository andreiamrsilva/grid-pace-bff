from abc import ABC, abstractmethod
from typing import List, Optional

from models.calendar import CalendarEvent
from models.event import Stage
from models.stage_times import StageStandings
from models.overall_standings import OverallStandings
from models.championship_standings import ChampionshipStandings, ChampionshipTeamStandings

class SportIngestionStrategy(ABC):
    """
    Generic interface for motorsport ingestion strategies.
    Any added sport (F1, WRC, MotoGP) must implement these methods.
    """
    
    @abstractmethod
    async def fetch_calendar_events(self, years: List[int]) -> List[CalendarEvent]:
        """Fetches the calendar events for a list of years."""
        pass

    @abstractmethod
    async def fetch_event_stages(self, event_id: int) -> List[Stage]:
        """Fetches the sessions/stages (Qualifying, Race, Stages) of a specific event."""
        pass

    @abstractmethod
    async def fetch_live_timing(self, event_id: int, stage_id: int) -> Optional[StageStandings]:
        """Fetches the live or final timing of a specific session/stage."""
        pass

    @abstractmethod
    async def fetch_overall_standings(self, event_id: int) -> Optional[OverallStandings]:
        """Fetches the overall standings of an event."""
        pass

    @abstractmethod
    async def fetch_driver_championship(self, year: int) -> Optional[ChampionshipStandings]:
        """Fetches the driver championship standings for a specific year."""
        pass

    @abstractmethod
    async def fetch_team_championship(self, year: int) -> Optional[ChampionshipTeamStandings]:
        """Fetches the team championship standings for a specific year."""
        pass


class IngestionRegistry:
    """
    Centralized registry for sport strategies.
    The main service will iterate over all instances registered here.
    """
    def __init__(self):
        self._strategies = {}

    def register(self, category: str, strategy: SportIngestionStrategy):
        self._strategies[category.lower()] = strategy

    def get_strategy(self, category: str) -> SportIngestionStrategy:
        strategy = self._strategies.get(category.lower())
        if not strategy:
            raise ValueError(f"Nenhuma estratégia registada para a categoria '{category}'")
        return strategy
        
    def get_all_categories(self) -> List[str]:
        return list(self._strategies.keys())

# Global instance to be populated by clients and used by the service
registry = IngestionRegistry()
