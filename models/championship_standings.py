from pydantic import BaseModel
from typing import Optional, List

class ChampionshipDriverStanding(BaseModel):
    """Represents a single driver's position in the overall championship standings."""
    position: Optional[int] = None
    driver_name: str
    team_name: Optional[str] = None
    logo_path: Optional[str] = None
    points: Optional[float] = None
    wins: Optional[int] = None

class ChampionshipStandings(BaseModel):
    """Represents the championship standings for a given year and category."""
    year: int
    category: str
    standings: List[ChampionshipDriverStanding]

class ChampionshipTeamStanding(BaseModel):
    """Represents a single team's position in the overall championship standings."""
    position: Optional[int] = None
    team_name: str
    logo_path: Optional[str] = None
    points: Optional[float] = None
    wins: Optional[int] = None

class ChampionshipTeamStandings(BaseModel):
    """Represents the team championship standings for a given year and category."""
    year: int
    category: str
    standings: List[ChampionshipTeamStanding]
