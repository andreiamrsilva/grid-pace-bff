from pydantic import BaseModel
from datetime import date
from typing import Optional


class CalendarEvent(BaseModel):
    id: int
    name: str
    category: str  # "WRC" or "F1"
    country: str
    country_image_url: Optional[str] = None
    start_date: date
    finish_date: date
    current_leader: Optional[str] = None
    current_leader_logo_path: Optional[str] = None
