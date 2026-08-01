from typing import Optional, List
from pydantic import BaseModel, Field

class TrackFeature(BaseModel):
    name: str = Field(description="Name of the feature, e.g., 'Big Jumps', 'High Speed', 'Gravel'")
    description: Optional[str] = None

class TrackInfo(BaseModel):
    track_id: str = Field(description="Internal ID or code for the track/stage")
    name: str = Field(description="Name of the track or stage")
    category: str = Field(description="E.g., 'WRC' or 'F1'")
    is_iconic: bool = Field(default=False, description="Whether this track or stage is considered iconic")
    description: Optional[str] = Field(default=None, description="Detailed description of the track/stage history or characteristics")
    features: List[TrackFeature] = Field(default_factory=list, description="Notable features of the track/stage")
    length_km: Optional[float] = Field(default=None, description="Length of the track in kilometers")
    corners: Optional[int] = Field(default=None, description="Number of corners (primarily for F1)")
    lap_record: Optional[str] = Field(default=None, description="Current lap record (primarily for F1)")
    surface: Optional[str] = Field(default=None, description="Main surface type (e.g., 'Tarmac', 'Gravel', 'Snow')")
