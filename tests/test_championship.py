import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from main import app
from core.security import verify_client_token, verify_app_check_token
from models.championship_standings import (
    ChampionshipStandings,
    ChampionshipDriverStanding,
    ChampionshipTeamStandings,
    ChampionshipTeamStanding,
)

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

MOCK_WRC_DRIVER_STANDINGS = ChampionshipStandings(
    year=2024,
    category="WRC",
    standings=[
        ChampionshipDriverStanding(
            position=1, driver_name="T. Neuville", team_name="Hyundai Shell Mobis WRT", points=225.0, wins=2
        ),
        ChampionshipDriverStanding(
            position=2, driver_name="O. Tänak", team_name="Hyundai Shell Mobis WRT", points=200.0, wins=1
        ),
    ]
)

MOCK_F1_DRIVER_STANDINGS = ChampionshipStandings(
    year=2024,
    category="F1",
    standings=[
        ChampionshipDriverStanding(
            position=1, driver_name="M. Verstappen", team_name="Red Bull Racing", points=437.0, wins=9
        ),
        ChampionshipDriverStanding(
            position=2, driver_name="L. Norris", team_name="McLaren", points=374.0, wins=3
        ),
    ]
)

MOCK_WRC_TEAM_STANDINGS = ChampionshipTeamStandings(
    year=2024,
    category="WRC",
    standings=[
        ChampionshipTeamStanding(position=1, team_name="Hyundai Shell Mobis WRT", points=526.0, wins=5),
        ChampionshipTeamStanding(position=2, team_name="Toyota Gazoo Racing WRT", points=511.0, wins=7),
    ]
)

MOCK_F1_TEAM_STANDINGS = ChampionshipTeamStandings(
    year=2024,
    category="F1",
    standings=[
        ChampionshipTeamStanding(position=1, team_name="McLaren", points=666.0, wins=5),
        ChampionshipTeamStanding(position=2, team_name="Ferrari", points=652.0, wins=5),
    ]
)

# --- Test Cases for /championship/drivers/{year} ---

@patch("api.routers.championship.get_cached_data", new_callable=AsyncMock)
@patch("api.routers.championship.fetch_wrc_championship_standings", new_callable=AsyncMock)
@patch("api.routers.championship.fetch_f1_championship_standings", new_callable=AsyncMock)
async def test_get_driver_championship_standings_success(
    mock_f1_fetch, mock_wrc_fetch, mock_get_cache
):
    """Test retrieving driver standings for multiple categories."""
    mock_get_cache.return_value = None
    mock_wrc_fetch.return_value = MOCK_WRC_DRIVER_STANDINGS
    mock_f1_fetch.return_value = MOCK_F1_DRIVER_STANDINGS

    response = client.get("/championship/drivers/2024?categories=WRC&categories=F1")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["category"] == "WRC"
    assert data[0]["standings"][0]["driver_name"] == "T. Neuville"
    assert data[1]["category"] == "F1"
    assert data[1]["standings"][0]["driver_name"] == "M. Verstappen"

@patch("api.routers.championship.get_cached_data", new_callable=AsyncMock)
async def test_get_driver_championship_standings_cache_hit(mock_get_cache):
    """Test retrieving driver standings from Redis cache."""
    mock_get_cache.return_value = MOCK_WRC_DRIVER_STANDINGS.model_dump(mode="json")

    response = client.get("/championship/drivers/2024?categories=WRC")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["category"] == "WRC"
    assert data[0]["standings"][0]["driver_name"] == "T. Neuville"

# --- Test Cases for /championship/teams/{year} ---

@patch("api.routers.championship.get_cached_data", new_callable=AsyncMock)
@patch("api.routers.championship.fetch_wrc_team_championship_standings", new_callable=AsyncMock)
@patch("api.routers.championship.fetch_f1_team_championship_standings", new_callable=AsyncMock)
async def test_get_team_championship_standings_success(
    mock_f1_fetch, mock_wrc_fetch, mock_get_cache
):
    """Test retrieving team standings for WRC and F1."""
    mock_get_cache.return_value = None
    mock_wrc_fetch.return_value = MOCK_WRC_TEAM_STANDINGS
    mock_f1_fetch.return_value = MOCK_F1_TEAM_STANDINGS

    response = client.get("/championship/teams/2024?categories=WRC&categories=F1")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["category"] == "WRC"
    assert data[0]["standings"][0]["team_name"] == "Hyundai Shell Mobis WRT"
    assert data[1]["category"] == "F1"
    assert data[1]["standings"][0]["team_name"] == "McLaren"
