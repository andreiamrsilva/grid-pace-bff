import httpx
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone, date, timedelta

from models.weather import WeatherForecast, HourlyWeather
from models.event_briefing import WeatherBriefing, WeatherDaySummary
from core.redis_service import get_cached_data, set_cached_data

logger = logging.getLogger(__name__)

OPEN_METEO_API_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_CACHE_TTL = 3600  # 1 hour cache duration
HTTP_HEADERS = {
    "User-Agent": "GridPaceBFF/1.0 (https://github.com/andreiamrsilva/grid-pace-bff)"
}

# Secondary in-memory cache to handle Redis failures or local burst requests
_MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}


def _round_coord(val: float) -> float:
    """Rounds coordinates to 2 decimal places to consolidate near-identical location cache keys."""
    return round(val, 2)


def _make_forecast_cache_key(latitude: float, longitude: float) -> str:
    return f"weather:forecast:{_round_coord(latitude)}:{_round_coord(longitude)}"


def _make_briefing_cache_key(
    latitude: float,
    longitude: float,
    start_date: Optional[date],
    finish_date: Optional[date],
    language: str
) -> str:
    s_str = start_date.isoformat() if start_date else "none"
    f_str = finish_date.isoformat() if finish_date else "none"
    return f"weather:briefing:{_round_coord(latitude)}:{_round_coord(longitude)}:{s_str}:{f_str}:{language.lower()}"


def _get_memory_cache(key: str, allow_stale: bool = False) -> Optional[Dict[str, Any]]:
    """Retrieves data from in-memory cache if valid or stale fallback requested."""
    entry = _MEMORY_CACHE.get(key)
    if not entry:
        return None
    now = datetime.now(timezone.utc).timestamp()
    if not allow_stale and now > entry["expires_at"]:
        return None
    return entry["data"]


def _set_memory_cache(key: str, data: Dict[str, Any], ttl: int = DEFAULT_CACHE_TTL):
    """Stores data in in-memory cache with an expiration timestamp."""
    _MEMORY_CACHE[key] = {
        "data": data,
        "expires_at": datetime.now(timezone.utc).timestamp() + ttl
    }


async def _get_cached_weather(key: str) -> Optional[Dict[str, Any]]:
    """Attempts to retrieve cached weather data from Redis or memory."""
    try:
        redis_data = await get_cached_data(key)
        if redis_data:
            return redis_data
    except Exception as e:
        logger.warning(f"Error accessing Redis for weather cache key '{key}': {e}")
    
    return _get_memory_cache(key, allow_stale=False)


async def _store_cached_weather(key: str, data: Dict[str, Any], ttl: int = DEFAULT_CACHE_TTL):
    """Stores weather data in both Redis and memory cache."""
    _set_memory_cache(key, data, ttl)
    try:
        await set_cached_data(key, data, expiration_seconds=ttl)
    except Exception as e:
        logger.warning(f"Failed to persist weather cache key '{key}' to Redis: {e}")


async def _get_stale_fallback(key: str) -> Optional[Dict[str, Any]]:
    """Retrieves stale cached data from memory fallback when external API rate limits (429) occur."""
    return _get_memory_cache(key, allow_stale=True)


async def fetch_weather_forecast(latitude: float, longitude: float) -> Optional[WeatherForecast]:
    """
    Fetches the weather forecast for a given location using Open-Meteo API.
    Utilizes Redis and in-memory caching to avoid HTTP 429 rate limit errors.
    """
    cache_key = _make_forecast_cache_key(latitude, longitude)
    
    # 1. Check Cache Layer
    cached_data = await _get_cached_weather(cache_key)
    if cached_data:
        try:
            return WeatherForecast(**cached_data)
        except Exception as e:
            logger.warning(f"Failed to parse cached WeatherForecast for {cache_key}: {e}")

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,precipitation_probability,rain,weather_code",
        "current": "temperature_2m,precipitation_probability,weather_code",
        "timezone": "UTC"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=HTTP_HEADERS) as client:
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

            forecast = WeatherForecast(
                latitude=data.get("latitude", latitude),
                longitude=data.get("longitude", longitude),
                elevation=data.get("elevation"),
                hourly=hourly_forecasts,
                current_temperature=current_data.get("temperature_2m"),
                current_precipitation_probability=current_data.get("precipitation_probability"),
                current_weather_code=current_data.get("weather_code")
            )

            # Store in cache
            await _store_cached_weather(cache_key, forecast.model_dump(mode='json'))
            return forecast

    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 429:
            logger.warning(
                f"Open-Meteo API rate limit (429 Too Many Requests) hit for ({latitude}, {longitude}). "
                f"Checking for stale cached weather fallback."
            )
            stale_data = await _get_stale_fallback(cache_key)
            if stale_data:
                try:
                    return WeatherForecast(**stale_data)
                except Exception as parse_err:
                    logger.error(f"Error parsing stale weather forecast cache: {parse_err}")
            return None
        logger.error(f"HTTP error fetching weather forecast from Open-Meteo for {latitude}, {longitude}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch weather forecast from Open-Meteo for {latitude}, {longitude}: {e}")
        stale_data = await _get_stale_fallback(cache_key)
        if stale_data:
            try:
                return WeatherForecast(**stale_data)
            except Exception:
                pass
        return None


WMO_WEATHER_MAP_PT = {
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

WMO_WEATHER_MAP_EN = {
    0: "Sunny / Clear Sky",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing Rime Fog",
    51: "Light Drizzle",
    53: "Moderate Drizzle",
    55: "Dense Drizzle",
    61: "Slight Rain",
    63: "Moderate Rain",
    65: "Heavy Rain",
    71: "Slight Snow Fall",
    73: "Moderate Snow Fall",
    75: "Heavy Snow Fall",
    80: "Slight Rain Showers",
    81: "Moderate Rain Showers",
    82: "Violent Rain Showers",
    95: "Thunderstorm",
    96: "Thunderstorm with Slight Hail",
    99: "Thunderstorm with Heavy Hail",
}


def get_wmo_condition_description(code: int, language: str = "pt") -> str:
    weather_map = WMO_WEATHER_MAP_EN if language.lower().startswith("en") else WMO_WEATHER_MAP_PT
    default_text = "Variable / Undetermined" if language.lower().startswith("en") else "Variável / Indeterminado"
    return weather_map.get(code, default_text)


async def fetch_event_weather_briefing(
    latitude: float,
    longitude: float,
    start_date: Optional[date] = None,
    finish_date: Optional[date] = None,
    language: str = "pt"
) -> Optional[WeatherBriefing]:
    """
    Fetches weather forecast for an event location and aggregates hourly data into a daily briefing.
    Utilizes Redis and in-memory caching to prevent Open-Meteo HTTP 429 rate limit issues.
    """
    cache_key = _make_briefing_cache_key(latitude, longitude, start_date, finish_date, language)

    # 1. Check Cache Layer
    cached_data = await _get_cached_weather(cache_key)
    if cached_data:
        try:
            return WeatherBriefing(**cached_data)
        except Exception as e:
            logger.warning(f"Failed to parse cached WeatherBriefing for {cache_key}: {e}")

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "timezone": "UTC"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=HTTP_HEADERS) as client:
            response = await client.get(OPEN_METEO_API_URL, params=params)
            response.raise_for_status()
            data = response.json()

            daily_data = data.get("daily", {})
            times = daily_data.get("time", [])
            t_max = daily_data.get("temperature_2m_max", [])
            t_min = daily_data.get("temperature_2m_min", [])
            precip_prob = daily_data.get("precipitation_probability_max", [])
            codes = daily_data.get("weather_code", [])

            all_forecast_days = []
            matching_forecast_days = []

            for i in range(len(times)):
                try:
                    d = date.fromisoformat(times[i])
                    weather_code = codes[i] if i < len(codes) and codes[i] is not None else 0
                    condition_str = get_wmo_condition_description(weather_code, language=language)

                    day_summary = WeatherDaySummary(
                        date=d,
                        temp_min=t_min[i] if i < len(t_min) and t_min[i] is not None else 0.0,
                        temp_max=t_max[i] if i < len(t_max) and t_max[i] is not None else 0.0,
                        rain_probability=precip_prob[i] if i < len(precip_prob) and precip_prob[i] is not None else 0,
                        weather_code=weather_code,
                        condition=condition_str
                    )

                    all_forecast_days.append(day_summary)

                    # Filter for event date range if specified
                    if start_date and d < start_date:
                        continue
                    if finish_date and d > finish_date:
                        continue

                    matching_forecast_days.append(day_summary)
                except (ValueError, IndexError) as e:
                    logger.warning(f"Error parsing daily weather forecast at index {i}: {e}")
                    continue

            # Only return forecast days that strictly match the event date range (start_date <= date <= finish_date)
            final_forecast = matching_forecast_days

            briefing = WeatherBriefing(
                latitude=data.get("latitude", latitude),
                longitude=data.get("longitude", longitude),
                forecast_days=final_forecast
            )

            # Store in cache
            await _store_cached_weather(cache_key, briefing.model_dump(mode='json'))
            return briefing

    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 429:
            logger.warning(
                f"Open-Meteo API rate limit (429 Too Many Requests) hit for ({latitude}, {longitude}). "
                f"Checking for stale cached weather briefing fallback."
            )
            stale_data = await _get_stale_fallback(cache_key)
            if stale_data:
                try:
                    return WeatherBriefing(**stale_data)
                except Exception as parse_err:
                    logger.error(f"Error parsing stale weather briefing cache: {parse_err}")
            return None
        logger.error(f"HTTP error fetching event weather briefing from Open-Meteo for {latitude}, {longitude}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch event weather briefing for {latitude}, {longitude}: {e}")
        stale_data = await _get_stale_fallback(cache_key)
        if stale_data:
            try:
                return WeatherBriefing(**stale_data)
            except Exception:
                pass
        return None
