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

WMO_WEATHER_MAP = {
    0: "Ensolarado / Céu Limpo",
    1: "Predominantemente Limpo",
    2: "Parcialmente Nublado",
    3: "Nublado",
    45: "Nevoeiro",
    48: "Nevoeiro com Geada",
    51: "Garoa Leve",
    53: "Garoa Moderada",
    55: "Garoa Densa",
    61: "Chuva Leve",
    63: "Chuva Moderada",
    65: "Chuva Forte",
    71: "Queda de Neve Leve",
    73: "Queda de Neve Moderada",
    75: "Queda de Neve Forte",
    80: "Pancadas de Chuva Leves",
    81: "Pancadas de Chuva Moderadas",
    82: "Pancadas de Chuva Violentas",
    95: "Trovoada",
    96: "Trovoada com Granizo Leve",
    99: "Trovoada com Granizo Forte",
}

def get_wmo_condition_description(code: int) -> str:
    return WMO_WEATHER_MAP.get(code, "Variável / Indeterminado")

from models.event_briefing import WeatherBriefing, WeatherDaySummary
from datetime import date, timedelta
from collections import defaultdict

async def fetch_event_weather_briefing(
    latitude: float,
    longitude: float,
    start_date: Optional[date] = None,
    finish_date: Optional[date] = None
) -> Optional[WeatherBriefing]:
    """
    Fetches weather forecast for an event location and aggregates hourly data into a daily briefing.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "timezone": "UTC"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(OPEN_METEO_API_URL, params=params)
            response.raise_for_status()
            data = response.json()

            daily_data = data.get("daily", {})
            times = daily_data.get("time", [])
            t_max = daily_data.get("temperature_2m_max", [])
            t_min = daily_data.get("temperature_2m_min", [])
            precip_prob = daily_data.get("precipitation_probability_max", [])
            codes = daily_data.get("weather_code", [])

            forecast_days = []
            for i in range(len(times)):
                try:
                    d = date.fromisoformat(times[i])
                    # Filter for event date range if specified
                    if start_date and d < start_date:
                        continue
                    if finish_date and d > finish_date:
                        continue

                    weather_code = codes[i] if i < len(codes) and codes[i] is not None else 0
                    condition_str = get_wmo_condition_description(weather_code)

                    forecast_days.append(
                        WeatherDaySummary(
                            date=d,
                            temp_min=t_min[i] if i < len(t_min) and t_min[i] is not None else 0.0,
                            temp_max=t_max[i] if i < len(t_max) and t_max[i] is not None else 0.0,
                            rain_probability=precip_prob[i] if i < len(precip_prob) and precip_prob[i] is not None else 0,
                            weather_code=weather_code,
                            condition=condition_str
                        )
                    )
                except (ValueError, IndexError) as e:
                    logger.warning(f"Error parsing daily weather forecast at index {i}: {e}")
                    continue

            return WeatherBriefing(
                latitude=data.get("latitude", latitude),
                longitude=data.get("longitude", longitude),
                forecast_days=forecast_days
            )

    except Exception as e:
        logger.error(f"Failed to fetch event weather briefing for {latitude}, {longitude}: {e}")
        return None

