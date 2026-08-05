import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone
from main import app
from core.security import verify_client_token, verify_app_check_token
from models.stage_times import StageStandings, DriverTime

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

MOCK_WRC_STANDINGS_11326 = StageStandings(
    stage_id=11326,
    event_id=644,
    category="WRC",
    is_live=False,
    standings=[
        DriverTime(entry_id=62981, driver_name="Sami PAJARI", logo_path="/logos/toyota.png", status="Finished", time="2h 27m 58.0s", position=1),
        DriverTime(entry_id=62982, driver_name="Oliver SOLBERG", logo_path="/logos/toyota.png", status="Finished", time="2h 28m 24.7s", position=2),
    ]
)

MOCK_F1_STANDINGS_11326 = StageStandings(
    stage_id=11326,
    event_id=1219,
    category="F1",
    is_live=False,
    standings=[
        DriverTime(entry_id=16, driver_name="Charles LECLERC", logo_path="/logos/ferrari.png", status="Finished", time="1h 27m 11.821s", position=1),
        DriverTime(entry_id=63, driver_name="George RUSSELL", logo_path="/logos/mercedes.png", status="Finished", time="1h 27m 12.103s", position=2),
    ]
)

@patch("api.routers.events.get_cached_data", new_callable=AsyncMock)
@patch("api.routers.events.get_stage_times_from_db", new_callable=AsyncMock)
@patch("api.routers.events.fetch_wrc_stage_times", new_callable=AsyncMock)
async def test_wrc_stage_times_returns_wrc_drivers(mock_fetch_wrc, mock_get_db, mock_get_cache):
    """Verify that requesting WRC stage 11326 returns WRC drivers and not F1 drivers."""
    mock_get_cache.return_value = None
    # DB has no valid WRC entries cached
    mock_get_db.return_value = None
    mock_fetch_wrc.return_value = MOCK_WRC_STANDINGS_11326

    response = client.get("/events/wrc/644/stages/11326/times")
    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "WRC"
    assert data["standings"][0]["driver_name"] == "Sami PAJARI"
    assert data["standings"][1]["driver_name"] == "Oliver SOLBERG"

@patch("api.routers.events.get_cached_data", new_callable=AsyncMock)
@patch("api.routers.events.get_stage_times_from_db", new_callable=AsyncMock)
async def test_category_isolation_db_hit(mock_get_db, mock_get_cache):
    """Verify that DB lookup filters by category and returns WRC standings."""
    mock_get_cache.return_value = None
    mock_get_db.return_value = MOCK_WRC_STANDINGS_11326

    response = client.get("/events/wrc/644/stages/11326/times")
    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "WRC"
    assert data["standings"][0]["driver_name"] == "Sami PAJARI"
