import httpx
import logging
from typing import Optional
from datetime import datetime, timezone
from models.weather import WeatherForecast, HourlyWeather

logger = logging.getLogger(__name__)

OPEN_METEO_API_URL = "https://api.open-meteo.com/v1/forecast"

async def fetch_weather_forecast(latitude: float, longitude: float) -> Optional[WeatherForecast]:
    """
    Fetches the weather forecast for a given location using Open-Meteo API.
    Retrieves temperature, precipitation probability, and weather codes.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,precipitation_probability,rain,weather_code",
        "current": "temperature_2m,precipitation_probability,weather_code",
        "timezone": "UTC"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(OPEN_METEO_API_URL, params=params)
            response.raise_for_status()
            data = response.json()

            hourly_data = data.get("hourly", {})
            times = hourly_data.get("time", [])
            temps = hourly_data.get("temperature_2m", [])
            precip_probs = hourly_data.get("precipitation_probability", [])
            rains = hourly_data.get("rain", [])
            weather_codes = hourly_data.get("weather_code", [])

            hourly_forecasts = []
            for i in range(len(times)):
                try:
                    dt = datetime.fromisoformat(times[i]).replace(tzinfo=timezone.utc)
                    hourly_forecasts.append(
                        HourlyWeather(
                            time=dt,
                            temperature=temps[i],
                            precipitation_probability=precip_probs[i],
                            rain=rains[i],
                            weather_code=weather_codes[i]
                        )
                    )
                except (ValueError, IndexError) as e:
                    logger.warning(f"Error parsing hourly weather data at index {i}: {e}")
                    continue

            current_data = data.get("current", {})

            return WeatherForecast(
                latitude=data.get("latitude", latitude),
                longitude=data.get("longitude", longitude),
                elevation=data.get("elevation"),
                hourly=hourly_forecasts,
                current_temperature=current_data.get("temperature_2m"),
                current_precipitation_probability=current_data.get("precipitation_probability"),
                current_weather_code=current_data.get("weather_code")
            )
            
    except Exception as e:
        logger.error(f"Failed to fetch weather from Open-Meteo for {latitude}, {longitude}: {e}")
        return None
