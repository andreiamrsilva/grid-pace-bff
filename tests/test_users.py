import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from main import app
from core.security import verify_client_token
from models.user import UserResponse, UserSettingsBase, CategorySetting

pytestmark = pytest.mark.asyncio

@pytest.fixture(autouse=True)
def override_security():
    async def mock_verify_client_token_pass():
        return {"uid": "test_user_uid_123", "email": "test@example.com"}
    app.dependency_overrides[verify_client_token] = mock_verify_client_token_pass
    yield
    app.dependency_overrides.clear()

client = TestClient(app)

MOCK_USER_RESPONSE = UserResponse(
    uid="test_user_uid_123",
    email="test@example.com",
    is_eternal_pro=False,
    subscription_active=True,
    settings=UserSettingsBase(
        categories=[CategorySetting(name="WRC", order=1), CategorySetting(name="F1", order=2)],
        notif_stage_live=True,
        notif_stage_comments=False
    )
)

MOCK_UPDATED_SETTINGS = UserSettingsBase(
    categories=[CategorySetting(name="F1", order=1)],
    notif_stage_live=False,
    notif_stage_comments=True
)

@patch("api.routers.users.get_or_create_user", new_callable=AsyncMock)
async def test_get_current_user_success(mock_get_user):
    """Test retrieving current user profile and settings."""
    mock_get_user.return_value = MOCK_USER_RESPONSE

    response = client.get("/api/v1/users/me")

    assert response.status_code == 200
    data = response.json()
    assert data["uid"] == "test_user_uid_123"
    assert data["email"] == "test@example.com"
    assert data["settings"]["notif_stage_live"] is True
    assert len(data["settings"]["categories"]) == 2

@patch("api.routers.users.update_user_settings_in_db", new_callable=AsyncMock)
async def test_update_current_user_settings_success(mock_update_settings):
    """Test updating user settings via PATCH /api/v1/users/me/settings."""
    mock_update_settings.return_value = MOCK_UPDATED_SETTINGS

    payload = {
        "categories": [{"name": "F1", "order": 1}],
        "notif_stage_live": False,
        "notif_stage_comments": True
    }

    response = client.patch("/api/v1/users/me/settings", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["notif_stage_live"] is False
    assert data["notif_stage_comments"] is True
    assert len(data["categories"]) == 1
    assert data["categories"][0]["name"] == "F1"
