import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

from main import app
from core.security import verify_client_token, verify_app_check_token
from models.timeline import TimelineEvent, TimelineEventSource, TimelineEventSeverity

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

MOCK_F1_TIMELINE_EVENT = TimelineEvent(
    id="f1_evt_1",
    timestamp=datetime(2024, 3, 2, 15, 30, tzinfo=timezone.utc),
    source=TimelineEventSource.F1_RACE_CONTROL,
    severity=TimelineEventSeverity.INFO,
    message="GREEN LIGHT - CLEAN TRACK",
    metadata={"message_pt": "LUZ VERDE - PISTA LIMPA"}
)

MOCK_WRC_TIMELINE_EVENT = TimelineEvent(
    id="wrc_evt_1",
    timestamp=datetime(2024, 1, 26, 10, 15, tzinfo=timezone.utc),
    source=TimelineEventSource.WRC_SYSTEM_INFERENCE,
    severity=TimelineEventSeverity.WARNING,
    message="T. Neuville is 2.5s faster at Split 2",
    metadata={"message_pt": "T. Neuville é 2.5s mais rápido no Intermédio 2"}
)

@patch("api.routers.timeline.get_cached_data", new_callable=AsyncMock)
async def test_get_f1_timeline_success(mock_get_cache):
    """Test successful retrieval of F1 timeline from cache."""
    mock_get_cache.return_value = [MOCK_F1_TIMELINE_EVENT.model_dump(mode="json")]

    response = client.get("/api/v1/timeline/f1/11326?event_id=202401&language=pt")

    assert response.status_code == 200
    data = response.json()
    assert data["event_id"] == "202401"
    assert data["session_id"] == "11326"
    assert len(data["events"]) == 1
    # Language localization mapping test
    assert data["events"][0]["message"] == "LUZ VERDE - PISTA LIMPA"

async def test_get_f1_timeline_invalid_session_id():
    """Test F1 timeline with non-integer session_id returns 400 Bad Request."""
    response = client.get("/api/v1/timeline/f1/invalid_id?event_id=202401")

    assert response.status_code == 400
    assert "F1 session_id must be an integer" in response.json()["detail"]

@patch("api.routers.timeline.get_cached_data", new_callable=AsyncMock)
async def test_get_wrc_timeline_success(mock_get_cache):
    """Test successful retrieval of WRC timeline from cache."""
    mock_get_cache.return_value = [MOCK_WRC_TIMELINE_EVENT.model_dump(mode="json")]

    response = client.get("/api/v1/timeline/wrc/101?event_id=1&language=en")

    assert response.status_code == 200
    data = response.json()
    assert data["event_id"] == "1"
    assert data["session_id"] == "101"
    assert len(data["events"]) == 1
    assert data["events"][0]["message"] == "T. Neuville is 2.5s faster at Split 2"

async def test_get_timeline_unsupported_category():
    """Test requesting timeline for unsupported category returns 404."""
    response = client.get("/api/v1/timeline/nascar/101?event_id=1")

    assert response.status_code == 404
    assert response.json() == {"detail": "Category not supported."}
