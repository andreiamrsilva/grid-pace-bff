from typing import Optional, List
from datetime import date as date_type, datetime
from pydantic import BaseModel, Field

class WeatherDaySummary(BaseModel):
    date: date_type = Field(description="Date of the weather forecast summary")
    temp_min: float = Field(description="Minimum temperature in Celsius")
    temp_max: float = Field(description="Maximum temperature in Celsius")
    rain_probability: int = Field(description="Maximum probability of precipitation in percentage")
    weather_code: int = Field(description="WMO weather interpretation code")
    condition: str = Field(description="Human-readable description of weather condition")

class WeatherBriefing(BaseModel):
    latitude: float = Field(description="Latitude of the event location")
    longitude: float = Field(description="Longitude of the event location")
    forecast_days: List[WeatherDaySummary] = Field(default_factory=list, description="Daily weather forecasts for event days")

class EventBriefing(BaseModel):
    event_id: int = Field(description="Event identifier")
    category: str = Field(description="Category of motorsport: 'F1' or 'WRC'")
    name: str = Field(description="Name of the circuit for F1 (e.g. 'Circuit de Monaco') or event for WRC (e.g. 'Rallye Monte-Carlo')")
    event_title: Optional[str] = Field(default=None, description="Full Grand Prix or Rally title (e.g. 'Formula 1 Grand Prix de Monaco 2026')")
    city: str = Field(description="City or region where the event takes place")
    country: str = Field(description="Country where the event takes place")
    country_image_url: Optional[str] = Field(default=None, description="URL for country flag or image")
    start_date: datetime = Field(description="Event start date and time")
    finish_date: datetime = Field(description="Event finish date and time")
    first_stage_name: Optional[str] = Field(default=None, description="Name of the first stage or session (e.g. 'Practice 1' or 'SS1 - SSS Monaco')")
    first_stage_start_time: Optional[datetime] = Field(default=None, description="Start time of the first stage or session")
    first_stage_location: Optional[str] = Field(default=None, description="Location of the first stage or session")
    surface_type: str = Field(description="Surface type (e.g., 'Asfalto', 'Terra', 'Neve/Gelo', 'Misto')")
    total_distance_km: Optional[float] = Field(default=None, description="Total distance in kilometers")
    laps_count: Optional[int] = Field(default=None, description="Number of laps (primarily for F1)")
    tactical_briefing: str = Field(description="Tactical analysis, key challenges, and strategic overview")
    last_winner: Optional[str] = Field(default=None, description="Last winner of the event (driver & team/manufacturer)")
    event_record: Optional[str] = Field(default=None, description="Lap record (F1) or historic record holder (WRC)")
    track_map_url: Optional[str] = Field(default=None, description="URL to the circuit layout or stage map image")
    track_map_svg: Optional[str] = Field(default=None, description="Optional raw SVG string or vector representation")
    weather: Optional[WeatherBriefing] = Field(default=None, description="Weather forecast during the event days")

