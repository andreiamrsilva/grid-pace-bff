import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from main import app
from core.security import verify_cron_secret

pytestmark = pytest.mark.asyncio

@pytest.fixture(autouse=True)
def override_cron_security():
    async def mock_cron_security_pass():
        return True
    app.dependency_overrides[verify_cron_secret] = mock_cron_security_pass
    yield
    app.dependency_overrides.clear()

client = TestClient(app)

@patch("ingestion.router.run_live_timing_ingestion", new_callable=AsyncMock)
async def test_cron_ingest_live_timing(mock_func):
    """Test GET /cron/ingest-live-timing trigger."""
    response = client.get("/cron/ingest-live-timing")
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    assert mock_func.called

@patch("ingestion.router.run_overall_standings_ingestion", new_callable=AsyncMock)
async def test_cron_ingest_overall_standings(mock_func):
    """Test GET /cron/ingest-overall-standings trigger."""
    response = client.get("/cron/ingest-overall-standings")
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    assert mock_func.called

@patch("ingestion.router.run_championship_standings_ingestion", new_callable=AsyncMock)
async def test_cron_ingest_championship(mock_func):
    """Test GET /cron/ingest-championship trigger."""
    response = client.get("/cron/ingest-championship")
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    assert mock_func.called

@patch("ingestion.router.run_historic_archive", new_callable=AsyncMock)
async def test_cron_archive_historic(mock_func):
    """Test GET /cron/archive-historic trigger."""
    response = client.get("/cron/archive-historic")
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    assert mock_func.called

@patch("ingestion.router.run_current_year_update", new_callable=AsyncMock)
async def test_cron_update_current_year(mock_func):
    """Test GET /cron/update-current-year trigger."""
    response = client.get("/cron/update-current-year")
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    assert mock_func.called

@patch("ingestion.router.run_timeline_validation_cron", new_callable=AsyncMock)
async def test_cron_validate_timeline_tweets(mock_func):
    """Test GET /cron/validate-timeline-tweets trigger."""
    response = client.get("/cron/validate-timeline-tweets")
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    assert mock_func.called

@patch("ingestion.router.run_briefing_generation_cron", new_callable=AsyncMock)
async def test_cron_generate_briefings(mock_func):
    """Test GET /cron/generate-briefings background task dispatch."""
    response = client.get("/cron/generate-briefings?force=true&limit=5")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

@patch("ingestion.router.run_stage_times_repair", new_callable=AsyncMock)
async def test_cron_repair_stage_times(mock_func):
    """Test GET /cron/repair-stage-times background task dispatch."""
    response = client.get("/cron/repair-stage-times?event_id=100&category=wrc")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
