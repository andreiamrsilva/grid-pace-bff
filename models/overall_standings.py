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
    position_change: Optional[int] = None # Positive for moving up, negative for dropping, 0 for no change

class OverallStandings(BaseModel):
    """Represents the overall standings for an entire event."""
    event_id: int
    category: str
    standings: List[OverallDriverStanding]
