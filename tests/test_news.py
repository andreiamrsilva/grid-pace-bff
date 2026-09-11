import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

from main import app
from core.security import verify_client_token, verify_app_check_token
from models.news import NewsArticle

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

MOCK_WRC_NEWS = NewsArticle(
    title="Neuville leads Rally Monte Carlo",
    summary="Thierry Neuville has taken the lead after Friday morning stages.",
    link="https://www.wrc.com/news/123",
    image_url="https://www.wrc.com/img.jpg",
    published_date=datetime(2024, 1, 26, 12, 0, tzinfo=timezone.utc),
    source="WRC"
)

MOCK_F1_NEWS = NewsArticle(
    title="Verstappen takes pole in Bahrain",
    summary="Max Verstappen qualified on pole position for the season opener.",
    link="https://www.formula1.com/news/456",
    image_url="https://www.formula1.com/img.jpg",
    published_date=datetime(2024, 3, 1, 16, 0, tzinfo=timezone.utc),
    source="F1"
)

@patch("api.routers.news.get_cached_data", new_callable=AsyncMock)
@patch("api.routers.news.fetch_news_from_feed", new_callable=AsyncMock)
@patch("api.routers.news.set_cached_data", new_callable=AsyncMock)
async def test_get_news_success(mock_set_cache, mock_fetch_feed, mock_get_cache):
    """Test fetching news for WRC and F1 on cache miss."""
    mock_get_cache.return_value = None
    
    async def fetch_side_effect(category, language):
        if category.lower() == "wrc":
            return [MOCK_WRC_NEWS]
        elif category.lower() == "f1":
            return [MOCK_F1_NEWS]
        return []

    mock_fetch_feed.side_effect = fetch_side_effect

    response = client.get("/news?categories=WRC&categories=F1&language=en")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    # Should be sorted chronologically descending by published_date
    assert data[0]["source"] == "F1"
    assert data[1]["source"] == "WRC"

@patch("api.routers.news.get_cached_data", new_callable=AsyncMock)
async def test_get_news_cache_hit(mock_get_cache):
    """Test retrieving news from Redis cache."""
    mock_get_cache.return_value = [MOCK_WRC_NEWS.model_dump(mode="json")]

    response = client.get("/news?categories=WRC&language=en")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Neuville leads Rally Monte Carlo"
