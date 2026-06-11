from pydantic import BaseModel
from datetime import date
from typing import Optional


class CalendarEvent(BaseModel):
    id: int
    name: str
    country: str
    country_image_url: Optional[str] = None
    start_date: date
    finish_date: date
    current_leader: Optional[str] = None
    current_leader_team_logo: Optional[str] = None
