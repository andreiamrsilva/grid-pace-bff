from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class Stage(BaseModel):
    id: int
    name: str
    number: int
    distance: float
    start_time: Optional[datetime] = None
    status: str
    is_live: bool = False
    winner_name: Optional[str] = None
    winner_team_logo: Optional[str] = None
    winner_time: Optional[str] = None
