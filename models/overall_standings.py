from pydantic import BaseModel
from typing import Optional, List

class OverallDriverStanding(BaseModel):
    """Represents a single driver's position in the overall event standings."""
    position: Optional[int] = None
    driver_name: str
    logo_path: Optional[str] = None
    time: Optional[str] = None
    diff_to_first: Optional[str] = None
    points: Optional[int] = None

class OverallStandings(BaseModel):
    """Represents the overall standings for an entire event."""
    event_id: int
    category: str
    standings: List[OverallDriverStanding]
