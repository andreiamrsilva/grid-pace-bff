import httpx
import logging
import asyncio
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, date, timedelta
from collections import defaultdict

from models.weather import WeatherForecast, HourlyWeather
from models.event_briefing import WeatherBriefing, WeatherDaySummary
from core.redis_service import get_cached_data, set_cached_data
from core.config import settings

logger = logging.getLogger(__name__)

# Base API URLs
OPEN_METEO_DEFAULT_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_CUSTOMER_URL = "https://customer-api.open-meteo.com/v1/forecast"
METNO_API_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
WTTR_API_URL = "https://wttr.in"

# Cache TTLs
DEFAULT_CACHE_TTL = 21600   # 6 hours cache for live weather forecasts to avoid exhausting API quotas
FALLBACK_CACHE_TTL = 1800   # 30 minutes cache duration for estimated seasonal fallbacks
CIRCUIT_BREAKER_TTL = 3600  # 1 hour cooldown when Open-Meteo daily request limit is exceeded

HTTP_HEADERS = {
    "User-Agent": "GridPaceBFF/1.0 (https://github.com/andreiamrsilva/grid-pace-bff)"
}

# Concurrency control semaphore to enforce max 1 parallel request to Open-Meteo free API
_OPENMETEO_SEMAPHORE = asyncio.Semaphore(1)

# In-memory circuit breaker timestamp (epoch seconds)
_OPENMETEO_BLOCKED_UNTIL: float = 0.0

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
    now = time.time()
    if not allow_stale and now > entry["expires_at"]:
        return None
    return entry["data"]


def _set_memory_cache(key: str, data: Dict[str, Any], ttl: int = DEFAULT_CACHE_TTL):
    """Stores data in in-memory cache with an expiration timestamp."""
    _MEMORY_CACHE[key] = {
        "data": data,
        "expires_at": time.time() + ttl
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


async def _is_openmeteo_circuit_open() -> bool:
    """Checks whether the Open-Meteo circuit breaker is currently active."""
    global _OPENMETEO_BLOCKED_UNTIL
    now = time.time()
    if _OPENMETEO_BLOCKED_UNTIL > now:
        return True

    # Also check Redis for multi-instance / serverless coordination
    try:
        blocked = await get_cached_data("weather:openmeteo:blocked")
        if blocked:
            _OPENMETEO_BLOCKED_UNTIL = now + CIRCUIT_BREAKER_TTL
            return True
    except Exception:
        pass

    return False


async def _trip_openmeteo_circuit_breaker(reason: str):
    """Trips the Open-Meteo circuit breaker when a daily quota limit or persistent block is detected."""
    global _OPENMETEO_BLOCKED_UNTIL
    # Block until midnight UTC or at least CIRCUIT_BREAKER_TTL
    now_utc = datetime.now(timezone.utc)
    midnight_utc = (now_utc + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    cooldown = max(CIRCUIT_BREAKER_TTL, int((midnight_utc - now_utc).total_seconds()))

    _OPENMETEO_BLOCKED_UNTIL = time.time() + cooldown
    logger.warning(
        f"Open-Meteo daily API quota exceeded ('{reason}'). "
        f"Circuit breaker activated for {cooldown // 3600}h. Directing weather requests to fallback providers."
    )
    try:
        await set_cached_data("weather:openmeteo:blocked", {"blocked": True, "reason": reason}, expiration_seconds=cooldown)
    except Exception:
        pass


# ==============================================================================
# WMO WEATHER CODES & TRANSLATIONS
# ==============================================================================

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

METNO_SYMBOLS_MAP = {
    "clearsky": (0, "Ensolarado / Céu Limpo", "Sunny / Clear Sky"),
    "fair": (1, "Predominantemente Limpo", "Mainly Clear"),
    "partlycloudy": (2, "Parcialmente Nublado", "Partly Cloudy"),
    "cloudy": (3, "Nublado", "Overcast"),
    "fog": (45, "Nevoeiro", "Fog"),
    "lightrain": (61, "Chuva Leve", "Slight Rain"),
    "lightrainshowers": (80, "Pancadas de Chuva Leves", "Slight Rain Showers"),
    "rain": (63, "Chuva Moderada", "Moderate Rain"),
    "rainshowers": (81, "Pancadas de Chuva Moderadas", "Moderate Rain Showers"),
    "heavyrain": (65, "Chuva Forte", "Heavy Rain"),
    "heavyrainshowers": (82, "Pancadas de Chuva Violentas", "Violent Rain Showers"),
    "lightrainandthunder": (95, "Trovoada com Chuva Leve", "Thunderstorm with Slight Rain"),
    "rainandthunder": (95, "Trovoada", "Thunderstorm"),
    "heavyrainandthunder": (99, "Trovoada Forte", "Heavy Thunderstorm"),
    "lightsleet": (68, "Chuva com Neve Leve", "Light Sleet"),
    "sleet": (68, "Chuva com Neve", "Sleet"),
    "heavysleet": (69, "Chuva com Neve Forte", "Heavy Sleet"),
    "lightsnow": (71, "Queda de Neve Leve", "Slight Snow Fall"),
    "snow": (73, "Queda de Neve Moderada", "Moderate Snow Fall"),
    "heavysnow": (75, "Queda de Neve Forte", "Heavy Snow Fall"),
}


def get_wmo_condition_description(code: int, language: str = "pt") -> str:
    weather_map = WMO_WEATHER_MAP_EN if language.lower().startswith("en") else WMO_WEATHER_MAP_PT
    default_text = "Variable / Undetermined" if language.lower().startswith("en") else "Variável / Indeterminado"
    return weather_map.get(code, default_text)


# ==============================================================================
# PROVIDER 1: OPEN-METEO
# ==============================================================================

async def _fetch_from_openmeteo(
    client: httpx.AsyncClient,
    params: Dict[str, Any],
    max_retries: int = 1
) -> Optional[Dict[str, Any]]:
    """
    Calls Open-Meteo API with concurrency lock (Semaphore), customer key support,
    and circuit breaker tripping on daily quota exhaustion.
    """
    if await _is_openmeteo_circuit_open():
        return None

    api_url = OPEN_METEO_CUSTOMER_URL if settings.OPEN_METEO_API_KEY else OPEN_METEO_DEFAULT_URL
    if settings.OPEN_METEO_API_KEY:
        params["apikey"] = settings.OPEN_METEO_API_KEY

    async with _OPENMETEO_SEMAPHORE:
        for attempt in range(max_retries + 1):
            try:
                response = await client.get(api_url, params=params)
                if response.status_code == 429:
                    reason = ""
                    try:
                        reason = response.json().get("reason", "")
                    except Exception:
                        pass

                    # Check if daily request quota was hit (shared IP on Vercel / serverless)
                    reason_lower = reason.lower()
                    if "daily" in reason_lower or "limit exceeded" in reason_lower or "tomorrow" in reason_lower:
                        await _trip_openmeteo_circuit_breaker(reason)
                        req = getattr(response, "request", None) or httpx.Request("GET", api_url)
                        raise httpx.HTTPStatusError(
                            f"429 Daily Limit: {reason}",
                            request=req,
                            response=response
                        )

                    # Momentary concurrency lock retry
                    if attempt < max_retries:
                        backoff = 1.0 * (2 ** attempt)
                        logger.warning(f"Open-Meteo concurrency 429 (attempt {attempt + 1}). Retrying in {backoff}s...")
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        req = getattr(response, "request", None) or httpx.Request("GET", api_url)
                        raise httpx.HTTPStatusError(
                            f"429 Too Many Requests: {reason}",
                            request=req,
                            response=response
                        )

                if response.status_code >= 400:
                    req = getattr(response, "request", None) or httpx.Request("GET", api_url)
                    raise httpx.HTTPStatusError(f"{response.status_code} Error", request=req, response=response)

                return response.json()
            except httpx.HTTPStatusError as e:
                if "Daily Limit" in str(e) or attempt == max_retries:
                    raise e
            except Exception as e:
                if attempt == max_retries:
                    raise e
    return None


async def _fetch_openmeteo_briefing(
    latitude: float,
    longitude: float,
    start_date: Optional[date],
    finish_date: Optional[date],
    language: str
) -> Optional[WeatherBriefing]:
    """Fetches weather briefing from Open-Meteo."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "timezone": "UTC"
    }

    try:
        async with httpx.AsyncClient(timeout=8.0, headers=HTTP_HEADERS) as client:
            data = await _fetch_from_openmeteo(client, params)
            if not data:
                return None

            daily_data = data.get("daily", {})
            times = daily_data.get("time", [])
            t_max = daily_data.get("temperature_2m_max", [])
            t_min = daily_data.get("temperature_2m_min", [])
            precip_prob = daily_data.get("precipitation_probability_max", [])
            codes = daily_data.get("weather_code", [])

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

                    if start_date and d < start_date:
                        continue
                    if finish_date and d > finish_date:
                        continue

                    matching_forecast_days.append(day_summary)
                except (ValueError, IndexError):
                    continue

            return WeatherBriefing(
                latitude=data.get("latitude", latitude),
                longitude=data.get("longitude", longitude),
                forecast_days=matching_forecast_days
            )
    except Exception as e:
        logger.debug(f"Open-Meteo briefing fetch failed: {e}")
        return None


async def _fetch_openmeteo_forecast(latitude: float, longitude: float) -> Optional[WeatherForecast]:
    """Fetches hourly weather forecast from Open-Meteo."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,precipitation_probability,rain,weather_code",
        "current": "temperature_2m,precipitation_probability,weather_code",
        "timezone": "UTC"
    }

    try:
        async with httpx.AsyncClient(timeout=8.0, headers=HTTP_HEADERS) as client:
            data = await _fetch_from_openmeteo(client, params)
            if not data:
                return None

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
                except (ValueError, IndexError):
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
        logger.debug(f"Open-Meteo forecast fetch failed: {e}")
        return None


# ==============================================================================
# PROVIDER 2: MET NORWAY (api.met.no) - Yr.no Engine
# ==============================================================================

async def _fetch_metno_briefing(
    latitude: float,
    longitude: float,
    start_date: Optional[date],
    finish_date: Optional[date],
    language: str
) -> Optional[WeatherBriefing]:
    """
    Fetches weather briefing from the official Norwegian Meteorological Institute (api.met.no).
    Highly reliable, free, with no shared-IP blockades.
    """
    params = {"lat": f"{latitude:.4f}", "lon": f"{longitude:.4f}"}
    is_en = language.lower().startswith("en")

    try:
        async with httpx.AsyncClient(timeout=8.0, headers=HTTP_HEADERS) as client:
            resp = await client.get(METNO_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            series = data.get("properties", {}).get("timeseries", [])
            if not series:
                return None

            days_data = defaultdict(lambda: {"temps": [], "precip": 0.0, "symbols": []})
            for p in series:
                time_str = p.get("time", "")
                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                d = dt.date()
                if start_date and d < start_date:
                    continue
                if finish_date and d > finish_date:
                    continue

                details = p.get("data", {}).get("instant", {}).get("details", {})
                temp = details.get("air_temperature")
                if temp is not None:
                    days_data[d]["temps"].append(temp)

                for period in ["next_1_hours", "next_6_hours", "next_12_hours"]:
                    p_data = p.get("data", {}).get(period, {})
                    p_details = p_data.get("details", {})
                    if "precipitation_amount" in p_details:
                        days_data[d]["precip"] += p_details["precipitation_amount"]
                    sym = p_data.get("summary", {}).get("symbol_code")
                    if sym:
                        days_data[d]["symbols"].append(sym)
                        break

            forecast_days: List[WeatherDaySummary] = []
            for d in sorted(days_data.keys()):
                info = days_data[d]
                temps = info["temps"]
                t_min = round(min(temps), 1) if temps else 0.0
                t_max = round(max(temps), 1) if temps else 0.0

                sym = info["symbols"][0] if info["symbols"] else "clearsky_day"
                base_sym = sym.split("_")[0]
                wmo_code, pt_desc, en_desc = METNO_SYMBOLS_MAP.get(
                    base_sym,
                    (0, "Ensolarado / Céu Limpo", "Sunny / Clear Sky")
                )
                condition_str = en_desc if is_en else pt_desc

                precip_mm = info["precip"]
                rain_prob = min(100, int(precip_mm * 20)) if precip_mm > 0 else (10 if "rain" in base_sym else 0)

                forecast_days.append(
                    WeatherDaySummary(
                        date=d,
                        temp_min=t_min,
                        temp_max=t_max,
                        rain_probability=rain_prob,
                        weather_code=wmo_code,
                        condition=condition_str
                    )
                )

            if not forecast_days:
                return None

            return WeatherBriefing(
                latitude=latitude,
                longitude=longitude,
                forecast_days=forecast_days
            )
    except Exception as e:
        logger.debug(f"MET Norway briefing fetch failed: {e}")
        return None


async def _fetch_metno_forecast(latitude: float, longitude: float) -> Optional[WeatherForecast]:
    """Fetches hourly weather forecast from MET Norway."""
    params = {"lat": f"{latitude:.4f}", "lon": f"{longitude:.4f}"}

    try:
        async with httpx.AsyncClient(timeout=8.0, headers=HTTP_HEADERS) as client:
            resp = await client.get(METNO_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            series = data.get("properties", {}).get("timeseries", [])
            if not series:
                return None

            cur_p = series[0]
            cur_details = cur_p.get("data", {}).get("instant", {}).get("details", {})
            cur_temp = cur_details.get("air_temperature")

            cur_sym = "clearsky_day"
            for period in ["next_1_hours", "next_6_hours"]:
                sym = cur_p.get("data", {}).get(period, {}).get("summary", {}).get("symbol_code")
                if sym:
                    cur_sym = sym
                    break

            base_sym = cur_sym.split("_")[0]
            cur_wmo = METNO_SYMBOLS_MAP.get(base_sym, (0,))[0]

            hourly_forecasts = []
            for p in series[:48]:  # Next 48 hours
                time_str = p.get("time", "")
                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                p_details = p.get("data", {}).get("instant", {}).get("details", {})
                t = p_details.get("air_temperature", 0.0)
                precip = p.get("data", {}).get("next_1_hours", {}).get("details", {}).get("precipitation_amount", 0.0)
                prob = min(100, int(precip * 20)) if precip > 0 else 0

                sym_hour = p.get("data", {}).get("next_1_hours", {}).get("summary", {}).get("symbol_code", "clearsky_day")
                h_wmo = METNO_SYMBOLS_MAP.get(sym_hour.split("_")[0], (0,))[0]

                hourly_forecasts.append(
                    HourlyWeather(
                        time=dt,
                        temperature=t,
                        precipitation_probability=prob,
                        rain=precip,
                        weather_code=h_wmo
                    )
                )

            return WeatherForecast(
                latitude=latitude,
                longitude=longitude,
                hourly=hourly_forecasts,
                current_temperature=cur_temp,
                current_precipitation_probability=0,
                current_weather_code=cur_wmo
            )
    except Exception as e:
        logger.debug(f"MET Norway forecast fetch failed: {e}")
        return None


# ==============================================================================
# PROVIDER 3: WTTR.IN (Fast JSON Fallback)
# ==============================================================================

async def _fetch_wttr_briefing(
    latitude: float,
    longitude: float,
    start_date: Optional[date],
    finish_date: Optional[date],
    language: str
) -> Optional[WeatherBriefing]:
    """Fetches weather briefing from wttr.in JSON API."""
    url = f"{WTTR_API_URL}/{latitude:.4f},{longitude:.4f}?format=j1"
    is_en = language.lower().startswith("en")

    try:
        async with httpx.AsyncClient(timeout=8.0, headers=HTTP_HEADERS) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

            weather_list = data.get("weather", [])
            forecast_days: List[WeatherDaySummary] = []

            for w in weather_list:
                d = date.fromisoformat(w.get("date", ""))
                if start_date and d < start_date:
                    continue
                if finish_date and d > finish_date:
                    continue

                t_min = float(w.get("mintempC", 0.0))
                t_max = float(w.get("maxtempC", 0.0))
                hourly = w.get("hourly", [])
                rain_prob = max([int(h.get("chanceofrain", 0)) for h in hourly]) if hourly else 0

                # Middle of the day condition description
                mid_idx = len(hourly) // 2
                desc_en = hourly[mid_idx]["weatherDesc"][0]["value"] if hourly else "Clear"
                cond_str = desc_en if is_en else _translate_wttr_desc_to_pt(desc_en)

                forecast_days.append(
                    WeatherDaySummary(
                        date=d,
                        temp_min=t_min,
                        temp_max=t_max,
                        rain_probability=rain_prob,
                        weather_code=0,
                        condition=cond_str
                    )
                )

            if not forecast_days:
                return None

            return WeatherBriefing(
                latitude=latitude,
                longitude=longitude,
                forecast_days=forecast_days
            )
    except Exception as e:
        logger.debug(f"wttr.in briefing fetch failed: {e}")
        return None


def _translate_wttr_desc_to_pt(desc: str) -> str:
    """Translates common wttr condition descriptions to Portuguese."""
    d = desc.lower().strip()
    if "sunny" in d or "clear" in d:
        return "Ensolarado / Céu Limpo"
    if "partly cloudy" in d:
        return "Parcialmente Nublado"
    if "cloudy" in d or "overcast" in d:
        return "Nublado"
    if "patchy rain" in d or "light rain" in d or "drizzle" in d:
        return "Chuva Leve"
    if "rain" in d or "shower" in d:
        return "Chuva Moderada"
    if "thunder" in d or "storm" in d:
        return "Trovoada"
    if "fog" in d or "mist" in d:
        return "Nevoeiro"
    if "snow" in d:
        return "Queda de Neve"
    return "Parcialmente Nublado"


# ==============================================================================
# FALLBACK: ESTIMATED SEASONAL FORECAST
# ==============================================================================

def _generate_estimated_weather_briefing(
    latitude: float,
    longitude: float,
    start_date: Optional[date] = None,
    finish_date: Optional[date] = None,
    language: str = "pt"
) -> WeatherBriefing:
    """Generates realistic seasonal estimated weather when all external APIs are unreachable."""
    is_en = language.lower().startswith("en")
    condition_str = "Previsão Estimada" if not is_en else "Estimated Forecast"

    target_start = start_date or date.today()
    target_finish = finish_date or (target_start + timedelta(days=2))
    month = target_start.month

    if abs(latitude) < 23.5:  # Tropical
        base_min, base_max = 22.0, 31.0
    elif month in (6, 7, 8):  # Northern Summer
        base_min, base_max = (18.0, 28.0) if latitude > 0 else (6.0, 16.0)
    elif month in (12, 1, 2):  # Northern Winter
        base_min, base_max = (5.0, 14.0) if latitude > 0 else (18.0, 29.0)
    else:  # Spring / Autumn
        base_min, base_max = 13.0, 23.0

    forecast_days = []
    curr = target_start
    while curr <= target_finish:
        forecast_days.append(
            WeatherDaySummary(
                date=curr,
                temp_min=base_min,
                temp_max=base_max,
                rain_probability=15,
                weather_code=1,
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
    """Generates seasonal fallback WeatherForecast."""
    now = datetime.now(timezone.utc)
    month = now.month
    if abs(latitude) < 23.5:
        base_min, base_max = 22.0, 31.0
    elif month in (6, 7, 8):
        base_min, base_max = (18.0, 28.0) if latitude > 0 else (6.0, 16.0)
    elif month in (12, 1, 2):
        base_min, base_max = (5.0, 14.0) if latitude > 0 else (18.0, 29.0)
    else:
        base_min, base_max = 13.0, 23.0

    avg_temp = round((base_min + base_max) / 2, 1)

    return WeatherForecast(
        latitude=latitude,
        longitude=longitude,
        elevation=0.0,
        hourly=[],
        current_temperature=avg_temp,
        current_precipitation_probability=15,
        current_weather_code=1
    )


# ==============================================================================
# PUBLIC API FUNCTIONS WITH MULTI-LAYER RESILIENCE
# ==============================================================================

async def fetch_event_weather_briefing(
    latitude: float,
    longitude: float,
    start_date: Optional[date] = None,
    finish_date: Optional[date] = None,
    language: str = "pt"
) -> Optional[WeatherBriefing]:
    """
    Fetches weather briefing for an event location with multi-provider resilience:
    1. Redis/Memory Cache (6h TTL)
    2. Open-Meteo API (with Concurrency Lock, Retries & Quota Circuit Breaker)
    3. MET Norway (Yr.no) API Fallback
    4. wttr.in Fallback
    5. Stale Cache Fallback
    6. Seasonal Estimated Fallback
    """
    cache_key = _make_briefing_cache_key(latitude, longitude, start_date, finish_date, language)

    # 1. Cache Layer
    cached_data = await _get_cached_weather(cache_key)
    if cached_data:
        try:
            return WeatherBriefing(**cached_data)
        except Exception as e:
            logger.warning(f"Failed to parse cached WeatherBriefing for {cache_key}: {e}")

    # 2. Try Open-Meteo
    briefing = await _fetch_openmeteo_briefing(latitude, longitude, start_date, finish_date, language)
    if briefing and briefing.forecast_days:
        await _store_cached_weather(cache_key, briefing.model_dump(mode='json'), ttl=DEFAULT_CACHE_TTL)
        return briefing

    # 3. Fallback: MET Norway (api.met.no)
    briefing = await _fetch_metno_briefing(latitude, longitude, start_date, finish_date, language)
    if briefing and briefing.forecast_days:
        logger.info(f"Serving weather briefing for ({latitude}, {longitude}) via MET Norway fallback.")
        await _store_cached_weather(cache_key, briefing.model_dump(mode='json'), ttl=DEFAULT_CACHE_TTL)
        return briefing

    # 4. Fallback: wttr.in
    briefing = await _fetch_wttr_briefing(latitude, longitude, start_date, finish_date, language)
    if briefing and briefing.forecast_days:
        logger.info(f"Serving weather briefing for ({latitude}, {longitude}) via wttr.in fallback.")
        await _store_cached_weather(cache_key, briefing.model_dump(mode='json'), ttl=DEFAULT_CACHE_TTL)
        return briefing

    # 5. Fallback: Stale Cache
    stale_data = await _get_stale_fallback(cache_key)
    if stale_data:
        try:
            logger.info(f"Serving stale cached weather briefing for ({latitude}, {longitude}).")
            return WeatherBriefing(**stale_data)
        except Exception:
            pass

    # 6. Fallback: Estimated Seasonal Forecast
    fallback = _generate_estimated_weather_briefing(latitude, longitude, start_date, finish_date, language)
    await _store_cached_weather(cache_key, fallback.model_dump(mode='json'), ttl=FALLBACK_CACHE_TTL)
    return fallback


async def fetch_weather_forecast(latitude: float, longitude: float) -> Optional[WeatherForecast]:
    """
    Fetches hourly weather forecast with multi-provider resilience:
    1. Redis/Memory Cache (6h TTL)
    2. Open-Meteo API
    3. MET Norway (Yr.no) API Fallback
    4. Stale Cache Fallback
    5. Seasonal Estimated Fallback
    """
    cache_key = _make_forecast_cache_key(latitude, longitude)

    # 1. Cache Layer
    cached_data = await _get_cached_weather(cache_key)
    if cached_data:
        try:
            return WeatherForecast(**cached_data)
        except Exception as e:
            logger.warning(f"Failed to parse cached WeatherForecast for {cache_key}: {e}")

    # 2. Try Open-Meteo
    forecast = await _fetch_openmeteo_forecast(latitude, longitude)
    if forecast:
        await _store_cached_weather(cache_key, forecast.model_dump(mode='json'), ttl=DEFAULT_CACHE_TTL)
        return forecast

    # 3. Fallback: MET Norway
    forecast = await _fetch_metno_forecast(latitude, longitude)
    if forecast:
        logger.info(f"Serving weather forecast for ({latitude}, {longitude}) via MET Norway fallback.")
        await _store_cached_weather(cache_key, forecast.model_dump(mode='json'), ttl=DEFAULT_CACHE_TTL)
        return forecast

    # 4. Fallback: Stale Cache
    stale_data = await _get_stale_fallback(cache_key)
    if stale_data:
        try:
            return WeatherForecast(**stale_data)
        except Exception:
            pass

    # 5. Fallback: Estimated Seasonal Forecast
    fallback = _generate_estimated_weather_forecast(latitude, longitude)
    await _store_cached_weather(cache_key, fallback.model_dump(mode='json'), ttl=FALLBACK_CACHE_TTL)
    return fallback
