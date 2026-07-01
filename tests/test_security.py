import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from main import app

client = TestClient(app)

def test_unauthenticated_request_returns_401():
    """
    Test that endpoints require a valid token and return 401 without it.
    """
    response = client.get("/calendar")
    assert response.status_code == 403 or response.status_code == 401
    
    # Check another endpoint
    response = client.get("/news?categories=F1")
    assert response.status_code == 403 or response.status_code == 401

@patch("core.security.app_check.verify_token")
@patch("core.security.auth.verify_id_token")
@patch("core.security.firebase_admin._apps", ["mock_app"])
def test_authenticated_request_calls_verify(mock_verify_id_token, mock_verify_app_check_token):
    """
    Test that sending a Bearer token and App Check token triggers both Firebase verifications.
    """
    mock_verify_id_token.return_value = {"uid": "test_user_123"}
    mock_verify_app_check_token.return_value = {"app_id": "test_app_123"}
    
    with patch("api.routers.calendar.get_all_events_from_db") as mock_db:
        mock_db.return_value = []
        response = client.get(
            "/calendar", 
            headers={
                "Authorization": "Bearer test_mock_token",
                "X-Firebase-AppCheck": "test_app_check_token"
            }
        )
        
        assert mock_verify_id_token.called
        assert mock_verify_id_token.call_args[0][0] == "test_mock_token"
        assert mock_verify_app_check_token.called
        assert mock_verify_app_check_token.call_args[0][0] == "test_app_check_token"
        assert response.status_code == 200

@patch("core.security.auth.verify_id_token")
@patch("core.security.firebase_admin._apps", ["mock_app"])
def test_authenticated_request_without_app_check(mock_verify_id_token):
    """
    Test that sending a Bearer token without App Check token fails.
    """
    mock_verify_id_token.return_value = {"uid": "test_user_123"}
    
    response = client.get(
        "/calendar", 
        headers={"Authorization": "Bearer test_mock_token"}
    )
    
    assert response.status_code == 401
    assert response.json()["detail"] == "App Check token is missing."
        
@patch("core.security.auth.verify_id_token")
@patch("core.security.firebase_admin._apps", ["mock_app"])
def test_authenticated_request_with_invalid_token(mock_verify_id_token):
    """
    Test that sending an invalid Bearer token returns 401.
    """
    mock_verify_id_token.side_effect = ValueError("Invalid token")
    
    response = client.get(
        "/calendar", 
        headers={
            "Authorization": "Bearer test_invalid_token",
            "X-Firebase-AppCheck": "test_app_check_token"
        }
    )
    
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid authentication credentials"
