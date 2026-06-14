import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
import httpx
from datetime import datetime

from main import app
from models.event import Stage
from models.stage_times import StageStandings, DriverTime

pytestmark = pytest.mark.asyncio

client = TestClient(app)

# --- Mock Data ---

MOCK_WRC_STAGE = Stage(
    id=101,
    name="Test Stage 1",
    number=1,
    distance=15.5,
    start_time=datetime(2024, 1, 25, 10, 0),
    status="Completed",
    is_live=False,
    winner_name="T. Neuville",
    winner_logo_path="/logos/hyundai.png",
    winner_time="10:05.1"
)

MOCK_F1_SESSION = Stage(
    id=2024011,
    name="Practice 1",
    number=1,
    distance=0.0,
    start_time=datetime(2024, 2, 29, 14, 30),
    status="Completed",
    is_live=False,
    winner_name="M. Verstappen",
    winner_logo_path="/logos/red_bull.png",
    winner_time="1:32.5"
)

MOCK_STANDINGS = StageStandings(
    stage_id=101,
    event_id=1,
    category="WRC",
    is_live=True,
    standings=[
        DriverTime(entry_id=1, driver_name="T. Neuville", logo_path="/logos/hyundai.png", status="Finished", time="10:05.1", position=1),
        DriverTime(entry_id=2, driver_name="S. Ogier", logo_path="/logos/toyota.png", status="OnTrack", time="08:12.0", last_split_id=3)
    ]
)

# --- Test Cases for /events/{category}/{event_id}/stages ---

@patch('api.routers.events.get_wrc_event_stages', new_callable=AsyncMock)
async def test_get_event_details_wrc_success(mock_wrc_stages):
    """Test successful retrieval of WRC stages."""
    mock_wrc_stages.return_value = [MOCK_WRC_STAGE]
    
    response = client.get("/events/wrc/1/stages")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]['name'] == "Test Stage 1"
    assert data[0]['winner_name'] == "T. Neuville"
    assert data[0]['winner_logo_path'] == "/logos/hyundai.png"

@patch('api.routers.events.get_wrc_event_stages', new_callable=AsyncMock)
async def test_get_event_details_wrc_not_found(mock_wrc_stages):
    """Test WRC event not found scenario."""
    # Simulate the HTTPException raised by the actual function when an event doesn't exist
    from fastapi import HTTPException
    mock_wrc_stages.side_effect = HTTPException(status_code=404, detail="Event not found")
    
    response = client.get("/events/wrc/999/stages")
    
    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}

@patch('api.routers.events.get_f1_event_sessions', new_callable=AsyncMock)
async def test_get_event_details_f1_success(mock_f1_sessions):
    """Test successful retrieval of F1 sessions."""
    mock_f1_sessions.return_value = [MOCK_F1_SESSION]
    
    response = client.get("/events/f1/202401/stages")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]['name'] == "Practice 1"
    assert data[0]['winner_logo_path'] == "/logos/red_bull.png"

async def test_get_event_details_invalid_category():
    """Test with an unsupported category."""
    response = client.get("/events/motoGP/1/stages")
    
    assert response.status_code == 404
    assert response.json() == {"detail": "Category not supported."}

async def test_get_event_details_f1_invalid_id():
    """Test F1 with invalid ID format."""
    response = client.get("/events/f1/abc/stages")
    
    assert response.status_code == 422 # FastAPI validation error for int

# --- Test Cases for /events/{category}/{event_id}/stages/{stage_id}/times ---

@patch('api.routers.events.get_wrc_stage_times', new_callable=AsyncMock)
async def test_get_stage_times_wrc_success(mock_wrc_times):
    """Test successful retrieval of live WRC stage times."""
    mock_wrc_times.return_value = MOCK_STANDINGS
    
    response = client.get("/events/wrc/1/stages/101/times")
    
    assert response.status_code == 200
    data = response.json()
    assert data['category'] == "WRC"
    assert data['is_live'] is True
    assert len(data['standings']) == 2
    
    # Check the first driver (Finished)
    assert data['standings'][0]['driver_name'] == "T. Neuville"
    assert data['standings'][0]['status'] == "Finished"
    assert data['standings'][0]['logo_path'] == "/logos/hyundai.png"
    
    # Check the second driver (On Track)
    assert data['standings'][1]['driver_name'] == "S. Ogier"
    assert data['standings'][1]['status'] == "OnTrack"

@patch('api.routers.events.get_wrc_stage_times', new_callable=AsyncMock)
async def test_get_stage_times_wrc_api_error(mock_wrc_times):
    """Test behavior when external API fails during live timing."""
    from fastapi import HTTPException
    mock_wrc_times.side_effect = HTTPException(status_code=502, detail="External API error.")
    
    response = client.get("/events/wrc/1/stages/101/times")
    
    assert response.status_code == 502
    assert response.json() == {"detail": "External API error."}
