from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class Stage(BaseModel):
    id: int
    event_id: Optional[int] = None
    name: str
    number: int
    distance: float
    start_time: Optional[datetime] = None
    status: str
    is_live: bool = False
    winner_name: Optional[str] = None
    winner_logo_path: Optional[str] = None
    winner_time: Optional[str] = None
    # Location & PEC Navigation Fields
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    google_maps_url: Optional[str] = None
