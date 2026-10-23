import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import date, datetime, timezone
import core.weather_service as ws
from core.weather_service import (
    fetch_weather_forecast,
    fetch_event_weather_briefing,
    _MEMORY_CACHE,
    _make_forecast_cache_key,
    _make_briefing_cache_key
)
from models.weather import WeatherForecast
from models.event_briefing import WeatherBriefing

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def reset_weather_state():
    _MEMORY_CACHE.clear()
    ws._OPENMETEO_BLOCKED_UNTIL = 0.0
    yield
    _MEMORY_CACHE.clear()
    ws._OPENMETEO_BLOCKED_UNTIL = 0.0


async def test_fetch_event_weather_briefing_success():
    mock_response_data = {
        "latitude": 45.6156,
        "longitude": 9.2811,
        "daily": {
            "time": ["2026-09-12", "2026-09-13"],
            "temperature_2m_max": [25.0, 24.5],
            "temperature_2m_min": [15.0, 14.0],
            "precipitation_probability_max": [10, 80],
            "weather_code": [0, 61]
        }
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await fetch_event_weather_briefing(45.6156, 9.2811, start_date=date(2026, 9, 12), finish_date=date(2026, 9, 13))

        assert res is not None
        assert isinstance(res, WeatherBriefing)
        assert len(res.forecast_days) == 2
        assert res.forecast_days[0].temp_max == 25.0
        assert res.forecast_days[0].condition == "Ensolarado / Céu Limpo"
        assert res.forecast_days[1].temp_max == 24.5
        assert res.forecast_days[1].condition == "Chuva Leve"

        # Verify second request uses cache (mock_get not called again)
        mock_get.reset_mock()
        cached_res = await fetch_event_weather_briefing(45.6156, 9.2811, start_date=date(2026, 9, 12), finish_date=date(2026, 9, 13))
        assert cached_res is not None
        mock_get.assert_not_called()


async def test_openmeteo_daily_429_activates_circuit_breaker_and_uses_metno_fallback():
    """
    When Open-Meteo returns 'Daily API request limit exceeded', the circuit breaker must trip,
    avoid futile retries, and seamlessly fall back to MET Norway.
    """
    # 1. Open-Meteo returns 429 Daily Limit
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.json.return_value = {"error": True, "reason": "Daily API request limit exceeded. Please try again tomorrow."}

    # 2. MET Norway returns 200 OK
    mock_resp_metno = MagicMock()
    mock_resp_metno.status_code = 200
    mock_resp_metno.json.return_value = {
        "properties": {
            "timeseries": [
                {
                    "time": "2026-10-24T12:00:00Z",
                    "data": {
                        "instant": {"details": {"air_temperature": 32.5}},
                        "next_1_hours": {
                            "summary": {"symbol_code": "clearsky_day"},
                            "details": {"precipitation_amount": 0.0}
                        }
                    }
                }
            ]
        }
    }
    mock_resp_metno.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [mock_resp_429, mock_resp_metno]

        res = await fetch_event_weather_briefing(
            21.6319, 39.1044,
            start_date=date(2026, 10, 24),
            finish_date=date(2026, 10, 24)
        )

        assert res is not None
        assert isinstance(res, WeatherBriefing)
        assert len(res.forecast_days) == 1
        assert res.forecast_days[0].temp_max == 32.5
        assert res.forecast_days[0].condition == "Ensolarado / Céu Limpo"

        # Verify circuit breaker was activated
        assert ws._OPENMETEO_BLOCKED_UNTIL > 0

        # Now test that subsequent requests do NOT call Open-Meteo at all
        mock_get.reset_mock()
        mock_get.side_effect = [mock_resp_metno]
        res2 = await fetch_event_weather_briefing(
            45.0, 9.0,
            start_date=date(2026, 10, 24),
            finish_date=date(2026, 10, 24)
        )
        assert res2 is not None
        # Only 1 call made (to MET Norway), Open-Meteo was bypassed by circuit breaker
        assert mock_get.call_count == 1


async def test_fetch_event_weather_briefing_http_429_with_stale_cache():
    cache_key = _make_briefing_cache_key(45.62, 9.28, date(2026, 9, 12), date(2026, 9, 13), "pt")
    _MEMORY_CACHE[cache_key] = {
        "data": {
            "latitude": 45.62,
            "longitude": 9.28,
            "forecast_days": [
                {
                    "date": "2026-09-12",
                    "temp_min": 15.0,
                    "temp_max": 25.0,
                    "rain_probability": 10,
                    "weather_code": 0,
                    "condition": "Ensolarado / Céu Limpo"
                }
            ]
        },
        "expires_at": 0  # Expired / stale timestamp
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.json.return_value = {"reason": "Daily limit exceeded"}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        # All providers fail
        mock_get.return_value = mock_resp

        res = await fetch_event_weather_briefing(45.62, 9.28, start_date=date(2026, 9, 12), finish_date=date(2026, 9, 13))

        assert res is not None
        assert isinstance(res, WeatherBriefing)
        assert len(res.forecast_days) == 1
        assert res.forecast_days[0].temp_max == 25.0


async def test_fetch_event_weather_briefing_all_fail_returns_estimated_fallback():
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.json.return_value = {"reason": "Daily limit exceeded"}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        res = await fetch_event_weather_briefing(40.3725, 49.8533, start_date=date(2026, 9, 22), finish_date=date(2026, 9, 24))

        # Must return an estimated WeatherBriefing instead of failing or returning None
        assert res is not None
        assert isinstance(res, WeatherBriefing)
        assert len(res.forecast_days) == 3
        assert "Estimada" in res.forecast_days[0].condition
