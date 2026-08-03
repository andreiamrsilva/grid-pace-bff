import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from datetime import date

from main import app
from core.security import verify_client_token, verify_app_check_token
from models.calendar import CalendarEvent

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

@patch('api.routers.calendar.get_all_events_from_db', new_callable=AsyncMock)
async def test_get_calendar_success(mock_get_db):
    """
    Test case for a successful call to the /calendar endpoint.
    """
    mock_get_db.return_value = [MOCK_WRC_EVENT, MOCK_F1_EVENT]

    response = client.get("/calendar")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

@patch('api.routers.calendar.get_all_events_from_db', new_callable=AsyncMock)
async def test_get_calendar_filtering(mock_get_db):
    """
    Test case for category and year filtering.
    """
    mock_get_db.return_value = [MOCK_WRC_EVENT, MOCK_F1_EVENT]

    response_wrc = client.get("/calendar?categories=WRC")
    assert response_wrc.status_code == 200
    data_wrc = response_wrc.json()
    assert len(data_wrc) == 1
    assert data_wrc[0]['category'] == 'WRC'

    response_f1 = client.get("/calendar?categories=F1")
    assert response_f1.status_code == 200
    data_f1 = response_f1.json()
    assert len(data_f1) == 1
    assert data_f1[0]['category'] == 'F1'

    response_year = client.get("/calendar?year=2030")
    assert response_year.status_code == 200
    assert len(response_year.json()) == 0
