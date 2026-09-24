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
FALLBACK_CACHE_TTL = 900   # 15 minutes cache duration for estimated fallback forecasts
HTTP_HEADERS = {
    "User-Agent": "GridPaceBFF/1.0 (https://github.com/andreiamrsilva/grid-pace-bff)"
}

# Concurrency control semaphore to enforce max 1 parallel request to Open-Meteo free API
_OPENMETEO_SEMAPHORE = asyncio.Semaphore(1)

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


async def _fetch_from_openmeteo_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: Dict[str, Any],
    max_retries: int = 2
) -> Optional[Dict[str, Any]]:
    """
    Executes HTTP GET against Open-Meteo API with concurrency control (Semaphore)
    and automatic retry backoff on 429 rate limit responses.
    """
    async with _OPENMETEO_SEMAPHORE:
        for attempt in range(max_retries + 1):
            try:
                response = await client.get(url, params=params)
                if response.status_code == 429:
                    reason = ""
                    try:
                        reason = response.json().get("reason", "")
                    except Exception:
                        pass

                    if attempt < max_retries:
                        backoff = 1.0 * (2 ** attempt)
                        logger.warning(
                            f"Open-Meteo API 429 Rate Limit (attempt {attempt + 1}/{max_retries + 1}). "
                            f"Reason: '{reason}'. Retrying in {backoff}s..."
                        )
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        logger.warning(
                            f"Open-Meteo API 429 Rate Limit persisted after {max_retries + 1} attempts. Reason: '{reason}'."
                        )
                        req = getattr(response, "request", None) or httpx.Request("GET", url)
                        raise httpx.HTTPStatusError(
                            f"429 Client Error: {reason or 'Too Many Requests'}",
                            request=req,
                            response=response
                        )

                if response.status_code >= 400:
                    req = getattr(response, "request", None) or httpx.Request("GET", url)
                    raise httpx.HTTPStatusError(
                        f"{response.status_code} Client Error",
                        request=req,
                        response=response
                    )

                return response.json()
            except httpx.HTTPStatusError as e:
                if attempt == max_retries:
                    raise e
            except Exception as e:
                if attempt == max_retries:
                    raise e
                await asyncio.sleep(0.5)
    return None


def _generate_estimated_weather_briefing(
    latitude: float,
    longitude: float,
    start_date: Optional[date] = None,
    finish_date: Optional[date] = None,
    language: str = "pt"
) -> WeatherBriefing:
    """
    Generates a realistic seasonal fallback weather briefing when external APIs are rate limited or unavailable.
    """
    is_en = language.lower().startswith("en")
    condition_str = "Previsão Estimada (Serviço Indisponível)" if not is_en else "Estimated Forecast (Service Unavailable)"

    target_start = start_date or date.today()
    target_finish = finish_date or (target_start + timedelta(days=2))
    month = target_start.month

    # Simple seasonal climate approximation based on latitude & month
    if abs(latitude) < 23.5:  # Tropical
        base_min, base_max = 22.0, 30.0
    elif month in (6, 7, 8):  # Northern Summer
        base_min, base_max = (18.0, 28.0) if latitude > 0 else (5.0, 15.0)
    elif month in (12, 1, 2):  # Northern Winter
        base_min, base_max = (4.0, 12.0) if latitude > 0 else (18.0, 28.0)
    else:  # Spring / Autumn
        base_min, base_max = 12.0, 22.0

    forecast_days = []
    curr = target_start
    while curr <= target_finish:
        forecast_days.append(
            WeatherDaySummary(
                date=curr,
                temp_min=base_min,
                temp_max=base_max,
                rain_probability=20,
                weather_code=2,
                condition=condition_str
            )
        )
        curr += timedelta(days=1)
        if len(forecast_days) >= 7:
            break

    return WeatherBriefing(
        latitude=latitude,
        longitude=longitude,
        forecast_days=forecast_days
    )


def _generate_estimated_weather_forecast(latitude: float, longitude: float) -> WeatherForecast:
    """Generates a seasonal fallback WeatherForecast when external APIs are rate limited or unavailable."""
    now = datetime.now(timezone.utc)
    month = now.month
    if abs(latitude) < 23.5:
        base_min, base_max = 22.0, 30.0
    elif month in (6, 7, 8):
        base_min, base_max = (18.0, 28.0) if latitude > 0 else (5.0, 15.0)
    elif month in (12, 1, 2):
        base_min, base_max = (4.0, 12.0) if latitude > 0 else (18.0, 28.0)
    else:
        base_min, base_max = 12.0, 22.0

    avg_temp = round((base_min + base_max) / 2, 1)

    return WeatherForecast(
        latitude=latitude,
        longitude=longitude,
        elevation=0.0,
        hourly=[],
        current_temperature=avg_temp,
        current_precipitation_probability=20,
        current_weather_code=2
    )


async def fetch_weather_forecast(latitude: float, longitude: float) -> Optional[WeatherForecast]:
    """
    Fetches the weather forecast for a given location using Open-Meteo API.
    Utilizes Redis, in-memory caching, concurrency locks, auto-retries, and seasonal fallbacks.
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
            data = await _fetch_from_openmeteo_with_retry(client, OPEN_METEO_API_URL, params)
            if not data:
                raise ValueError("Empty data returned from Open-Meteo API")

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
            await _store_cached_weather(cache_key, forecast.model_dump(mode='json'), ttl=DEFAULT_CACHE_TTL)
            return forecast

    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 429:
            logger.warning(
                f"Open-Meteo API rate limit (429) persisted for ({latitude}, {longitude}). "
                f"Attempting stale cache fallback or estimated forecast."
            )
            stale_data = await _get_stale_fallback(cache_key)
            if stale_data:
                try:
                    return WeatherForecast(**stale_data)
                except Exception as parse_err:
                    logger.error(f"Error parsing stale weather forecast cache: {parse_err}")

            fallback = _generate_estimated_weather_forecast(latitude, longitude)
            await _store_cached_weather(cache_key, fallback.model_dump(mode='json'), ttl=FALLBACK_CACHE_TTL)
            return fallback

        logger.error(f"HTTP error fetching weather forecast from Open-Meteo for {latitude}, {longitude}: {e}")
        fallback = _generate_estimated_weather_forecast(latitude, longitude)
        return fallback

    except Exception as e:
        logger.error(f"Failed to fetch weather forecast from Open-Meteo for {latitude}, {longitude}: {e}")
        stale_data = await _get_stale_fallback(cache_key)
        if stale_data:
            try:
                return WeatherForecast(**stale_data)
            except Exception:
                pass

        fallback = _generate_estimated_weather_forecast(latitude, longitude)
        return fallback


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
    Utilizes Redis, in-memory caching, concurrency locks, auto-retries, and seasonal fallbacks.
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
            data = await _fetch_from_openmeteo_with_retry(client, OPEN_METEO_API_URL, params)
            if not data:
                raise ValueError("Empty data returned from Open-Meteo API")

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

            final_forecast = matching_forecast_days

            briefing = WeatherBriefing(
                latitude=data.get("latitude", latitude),
                longitude=data.get("longitude", longitude),
                forecast_days=final_forecast
            )

            # Store in cache
            await _store_cached_weather(cache_key, briefing.model_dump(mode='json'), ttl=DEFAULT_CACHE_TTL)
            return briefing

    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 429:
            logger.warning(
                f"Open-Meteo API rate limit (429) persisted for ({latitude}, {longitude}). "
                f"Attempting stale cache fallback or estimated briefing."
            )
            stale_data = await _get_stale_fallback(cache_key)
            if stale_data:
                try:
                    return WeatherBriefing(**stale_data)
                except Exception as parse_err:
                    logger.error(f"Error parsing stale weather briefing cache: {parse_err}")

            fallback = _generate_estimated_weather_briefing(latitude, longitude, start_date, finish_date, language)
            await _store_cached_weather(cache_key, fallback.model_dump(mode='json'), ttl=FALLBACK_CACHE_TTL)
            return fallback

        logger.error(f"HTTP error fetching event weather briefing from Open-Meteo for {latitude}, {longitude}: {e}")
        fallback = _generate_estimated_weather_briefing(latitude, longitude, start_date, finish_date, language)
        return fallback

    except Exception as e:
        logger.error(f"Failed to fetch event weather briefing for {latitude}, {longitude}: {e}")
        stale_data = await _get_stale_fallback(cache_key)
        if stale_data:
            try:
                return WeatherBriefing(**stale_data)
            except Exception:
                pass

        fallback = _generate_estimated_weather_briefing(latitude, longitude, start_date, finish_date, language)
        return fallback
