from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class DriverTime(BaseModel):
    entry_id: int
    driver_name: str
    logo_path: Optional[str] = None
    status: str  # e.g., "Finished", "OnTrack", "Retired", "DidNotStart", "Scheduled"
    time: Optional[str] = None  # Formatted string like "12:45.3" or "+1.2"
    diff_to_first: Optional[str] = None
    position: Optional[int] = None
    position_change: Optional[int] = None # Positive for moving up, negative for dropping, 0 for no change

    # Additional fields to help order OnTrack drivers
    last_split_id: Optional[int] = None

class StageStandings(BaseModel):
    stage_id: int
    event_id: int
    category: str
    is_live: bool
    last_updated: Optional[datetime] = None
    standings: List[DriverTime]
