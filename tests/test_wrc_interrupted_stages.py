import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone
from main import app
from core.security import verify_client_token, verify_app_check_token
from models.event import Stage

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

MOCK_INTERRUPTED_STAGES = [
    Stage(
        id=101,
        event_id=455,
        name="Harju 1",
        number=1,
        distance=3.4,
        start_time=datetime(2024, 8, 1, 12, 0, tzinfo=timezone.utc),
        status="Completed",
        is_live=False,
    ),
    Stage(
        id=102,
        event_id=455,
        name="Laajavuori 2",
        number=2,
        distance=8.7,
        start_time=datetime(2024, 8, 4, 12, 0, tzinfo=timezone.utc),
        status="Interrupted",
        is_live=False,
    ),
]

@patch("api.routers.events.get_cached_data", new_callable=AsyncMock)
@patch("api.routers.events.get_stages_from_db", new_callable=AsyncMock)
@patch("api.routers.events.fetch_wrc_event_stages", new_callable=AsyncMock)
@patch("core.database_service.save_stages_to_db", new_callable=AsyncMock)
async def test_interrupted_stage_terminal_status(mock_save_db, mock_fetch_stages, mock_get_db, mock_get_cache):
    """Verify that an event with its final stage marked as Interrupted is correctly classified as a past event."""
    mock_get_cache.return_value = None
    mock_get_db.return_value = None
    mock_fetch_stages.return_value = MOCK_INTERRUPTED_STAGES

    response = client.get("/events/wrc/455/stages")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[-1]["status"] == "Interrupted"

@patch("api.routers.events.get_cached_data", new_callable=AsyncMock)
@patch("api.routers.events.get_stages_from_db", new_callable=AsyncMock)
async def test_interrupted_stage_db_hit(mock_get_db, mock_get_cache):
    """Verify that a DB hit returns stages when the last stage is Interrupted."""
    mock_get_cache.return_value = None
    mock_get_db.return_value = MOCK_INTERRUPTED_STAGES

    response = client.get("/events/wrc/455/stages")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[-1]["status"] == "Interrupted"
