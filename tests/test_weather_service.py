import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import date, datetime, timezone
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
def clear_memory_cache():
    _MEMORY_CACHE.clear()
    yield
    _MEMORY_CACHE.clear()


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


async def test_fetch_event_weather_briefing_retry_on_429_success():
    """Test that a momentary 429 retries and succeeds on the second attempt."""
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.json.return_value = {"reason": "Concurrent request limit"}

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = {
        "latitude": 40.3725,
        "longitude": 49.8533,
        "daily": {
            "time": ["2026-09-22"],
            "temperature_2m_max": [26.5],
            "temperature_2m_min": [18.0],
            "precipitation_probability_max": [0],
            "weather_code": [0]
        }
    }
    mock_resp_200.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [mock_resp_429, mock_resp_200]

        res = await fetch_event_weather_briefing(40.3725, 49.8533, start_date=date(2026, 9, 22), finish_date=date(2026, 9, 22))

        assert res is not None
        assert isinstance(res, WeatherBriefing)
        assert len(res.forecast_days) == 1
        assert res.forecast_days[0].temp_max == 26.5
        assert mock_get.call_count == 2


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
    req = httpx.Request("GET", "https://api.open-meteo.com/v1/forecast")
    http_err = httpx.HTTPStatusError("429 Client Error: Too Many Requests", request=req, response=mock_resp)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = http_err

        res = await fetch_event_weather_briefing(45.62, 9.28, start_date=date(2026, 9, 12), finish_date=date(2026, 9, 13))

        assert res is not None
        assert isinstance(res, WeatherBriefing)
        assert len(res.forecast_days) == 1
        assert res.forecast_days[0].temp_max == 25.0


async def test_fetch_event_weather_briefing_http_429_returns_estimated_fallback():
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
