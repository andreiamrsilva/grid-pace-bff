import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from datetime import date, datetime

from main import app
from core.security import verify_client_token, verify_app_check_token
from models.event_briefing import EventBriefing, WeatherBriefing, WeatherDaySummary

pytestmark = pytest.mark.asyncio

@pytest.fixture(autouse=True)
def override_security():
    async def mock_security_pass():
        return True
    app.dependency_overrides[verify_client_token] = mock_security_pass
    app.dependency_overrides[verify_app_check_token] = mock_security_pass
    yield
    app.dependency_overrides.clear()

client = TestClient(app)

MOCK_F1_BRIEFING = EventBriefing(
    event_id=9158,
    category="F1",
    name="Circuit de Monaco",
    event_title="Grand Prix de Monaco 2026",
    city="Monte Carlo",
    country="Monaco",
    country_image_url="https://flag.png",
    start_date=date(2026, 5, 22),
    finish_date=date(2026, 5, 24),
    first_stage_name="Practice 1",
    first_stage_start_time=datetime(2026, 5, 22, 13, 30),
    first_stage_location="Monte Carlo, Monaco",
    surface_type="Asfalto (Circuito de Rua)",
    total_distance_km=260.286,
    laps_count=78,
    tactical_briefing="O GP de Mónaco é a prova mais exigente em termos de precisão técnica.",
    last_winner="Charles Leclerc (Ferrari)",
    event_record="1:12.909 - Lewis Hamilton (2021)",
    track_map_url="https://media.formula1.com/monaco.png",
    weather=WeatherBriefing(
        latitude=43.7347,
        longitude=7.4206,
        forecast_days=[
            WeatherDaySummary(
                date=date(2026, 5, 22),
                temp_min=18.5,
                temp_max=24.0,
                rain_probability=10,
                weather_code=0,
                condition="Ensolarado / Céu Limpo"
            )
        ]
    )
)

MOCK_WRC_BRIEFING = EventBriefing(
    event_id=20261,
    category="WRC",
    name="Vodafone Rally de Portugal",
    event_title="Vodafone Rally de Portugal 2026",
    city="Matosinhos",
    country="Portugal",
    start_date=date(2026, 5, 14),
    finish_date=date(2026, 5, 17),
    first_stage_name="SS1 - Figueira da Foz",
    first_stage_start_time=datetime(2026, 5, 14, 17, 5),
    first_stage_location="Matosinhos, Portugal",
    surface_type="Terra",
    total_distance_km=337.04,
    laps_count=None,
    tactical_briefing="Troços técnicos em terra no norte e centro de Portugal.",
    last_winner="Sébastien Ogier (Toyota)",
    event_record="Sébastien Ogier - 6 Vitórias",
    track_map_url="https://www.wrc.com/maps_portugal.png",
    weather=None
)

@patch('api.routers.events.get_event_briefing', new_callable=AsyncMock)
async def test_get_event_briefing_f1_success(mock_get_briefing):
    """Test successful retrieval of F1 event briefing."""
    mock_get_briefing.return_value = MOCK_F1_BRIEFING

    response = client.get("/events/f1/9158/briefing")

    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "F1"
    assert data["name"] == "Circuit de Monaco"
    assert data["city"] == "Monte Carlo"
    assert data["country"] == "Monaco"
    assert data["first_stage_name"] == "Practice 1"
    assert data["first_stage_start_time"] == "2026-05-22T13:30:00"
    assert data["first_stage_location"] == "Monte Carlo, Monaco"
    assert data["surface_type"] == "Asfalto (Circuito de Rua)"
    assert data["total_distance_km"] == 260.286
    assert data["laps_count"] == 78
    assert "Charles Leclerc" in data["last_winner"]
    assert "1:12.909" in data["event_record"]
    assert data["track_map_url"] == "https://media.formula1.com/monaco.png"
    assert data["weather"] is not None
    assert len(data["weather"]["forecast_days"]) == 1
    assert data["weather"]["forecast_days"][0]["condition"] == "Ensolarado / Céu Limpo"

@patch('api.routers.events.get_event_briefing', new_callable=AsyncMock)
async def test_get_event_briefing_wrc_success(mock_get_briefing):
    """Test successful retrieval of WRC event briefing."""
    mock_get_briefing.return_value = MOCK_WRC_BRIEFING

    response = client.get("/events/wrc/20261/briefing")

    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "WRC"
    assert data["name"] == "Vodafone Rally de Portugal"
    assert data["first_stage_name"] == "SS1 - Figueira da Foz"
    assert data["laps_count"] is None
    assert data["surface_type"] == "Terra"
    assert data["total_distance_km"] == 337.04
    assert data["track_map_url"] == "https://www.wrc.com/maps_portugal.png"

async def test_get_event_briefing_invalid_category():
    """Test briefing endpoint with invalid category."""
    response = client.get("/events/nascar/100/briefing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Category not supported."}
