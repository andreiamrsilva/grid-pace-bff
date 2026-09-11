import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_root_endpoint():
    """
    Test case for the root endpoint GET /.
    Verifies that the endpoint returns a 200 HTTP status and welcome message.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to Grid Pace BFF API"}
