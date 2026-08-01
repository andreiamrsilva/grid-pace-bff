from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class HourlyWeather(BaseModel):
    time: datetime = Field(description="Time of the forecast")
    temperature: float = Field(description="Temperature in Celsius")
    precipitation_probability: int = Field(description="Probability of precipitation in percentage")
    rain: float = Field(description="Rain in mm")
    weather_code: int = Field(description="WMO Weather interpretation code")

class WeatherForecast(BaseModel):
    latitude: float
    longitude: float
    elevation: Optional[float] = None
    hourly: List[HourlyWeather] = Field(default_factory=list)
    current_temperature: Optional[float] = None
    current_precipitation_probability: Optional[int] = None
    current_weather_code: Optional[int] = None
