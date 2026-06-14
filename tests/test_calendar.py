import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
import httpx
from datetime import date

from main import app
from models.calendar import CalendarEvent

# Use pytest-asyncio for async tests
pytestmark = pytest.mark.asyncio

client = TestClient(app)

# --- Mock Data ---
MOCK_WRC_EVENT = CalendarEvent(
    id=1, name="Rally Monte Carlo", category="WRC", country="Monaco",
    start_date=date(2024, 1, 25), finish_date=date(2024, 1, 28),
    country_image_url="/logos/mc.png", current_leader="T. Neuville", current_leader_logo_path="/logos/hyundai.png"
)
MOCK_F1_EVENT = CalendarEvent(
    id=202401, name="Bahrain Grand Prix", category="F1", country="Bahrain",
    start_date=date(2024, 2, 29), finish_date=date(2024, 3, 2),
    country_image_url="/logos/bh.png", current_leader="M. Verstappen", current_leader_logo_path="/logos/red_bull.png"
)

# --- Test Cases ---

@patch('api.routers.calendar.fetch_wrc_events_for_years', new_callable=AsyncMock)
@patch('api.routers.calendar.get_f1_calendar_events', new_callable=AsyncMock)
@patch('api.routers.calendar.get_historic_events_from_db')
async def test_get_calendar_success(mock_get_db, mock_f1_events, mock_wrc_events):
    """
    Test case for a successful call to the /calendar endpoint.
    It mocks the external API calls and DB, then validates the response.
    """
    # 1. Setup: Configure mocks to return successful data
    mock_wrc_events.return_value = [MOCK_WRC_EVENT]
    mock_f1_events.return_value = [MOCK_F1_EVENT]
    mock_get_db.return_value = [] # Assume DB is empty for this test

    # 2. Act: Call the endpoint
    from api.routers import calendar
    # Manually trigger the cache update
    await calendar.update_recent_cache()
    
    response = client.get("/calendar")

    # 3. Assert: Validate the response
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    
    # Check for WRC event
    wrc_event_in_response = next((item for item in data if item['category'] == 'WRC'), None)
    assert wrc_event_in_response is not None
    assert wrc_event_in_response['name'] == "Rally Monte Carlo"
    
    # Check for F1 event
    f1_event_in_response = next((item for item in data if item['category'] == 'F1'), None)
    assert f1_event_in_response is not None
    assert f1_event_in_response['name'] == "Bahrain Grand Prix"

@patch('api.routers.calendar.fetch_wrc_events_for_years', new_callable=AsyncMock)
@patch('api.routers.calendar.get_f1_calendar_events', new_callable=AsyncMock)
@patch('api.routers.calendar.get_historic_events_from_db')
async def test_get_calendar_wrc_api_down(mock_get_db, mock_f1_events, mock_wrc_events):
    """
    Test case for when the WRC API is down.
    The endpoint should still return F1 data and not crash.
    """
    # 1. Setup: Mock WRC to fail and F1 to succeed
    mock_wrc_events.side_effect = httpx.RequestError("API is down", request=None)
    mock_f1_events.return_value = [MOCK_F1_EVENT]
    mock_get_db.return_value = []

    # 2. Act: Call the endpoint
    from api.routers import calendar
    await calendar.update_recent_cache()
    
    response = client.get("/calendar")

    # 3. Assert: Validate that the response is still successful but only contains F1 data
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]['category'] == 'F1'
    assert data[0]['name'] == "Bahrain Grand Prix"

@patch('api.routers.calendar.fetch_wrc_events_for_years', new_callable=AsyncMock)
@patch('api.routers.calendar.get_f1_calendar_events', new_callable=AsyncMock)
@patch('api.routers.calendar.get_historic_events_from_db')
async def test_get_calendar_filtering(mock_get_db, mock_f1_events, mock_wrc_events):
    """
    Test case for category and year filtering.
    """
    # 1. Setup
    mock_wrc_events.return_value = [MOCK_WRC_EVENT]
    mock_f1_events.return_value = [MOCK_F1_EVENT]
    mock_get_db.return_value = []

    # 2. Act & Assert for WRC category
    from api.routers import calendar
    await calendar.update_recent_cache()
    
    response_wrc = client.get("/calendar?categories=WRC")
    assert response_wrc.status_code == 200
    data_wrc = response_wrc.json()
    assert len(data_wrc) == 1
    assert data_wrc[0]['category'] == 'WRC'

    # 3. Act & Assert for F1 category
    response_f1 = client.get("/calendar?categories=F1")
    assert response_f1.status_code == 200
    data_f1 = response_f1.json()
    assert len(data_f1) == 1
    assert data_f1[0]['category'] == 'F1'
    
    # 4. Act & Assert for a year that has no events
    response_year = client.get("/calendar?year=2030")
    assert response_year.status_code == 200
    assert len(response_year.json()) == 0
