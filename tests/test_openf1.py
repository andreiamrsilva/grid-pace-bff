import pytest
from unittest.mock import patch, AsyncMock
from ingestion.openf1_client import fetch_f1_session_times, get_race_winner_from_openf1

pytestmark = pytest.mark.asyncio

MOCK_DRIVERS = [
    {"driver_number": 16, "full_name": "Charles LECLERC", "team_name": "Ferrari"},
    {"driver_number": 63, "full_name": "George RUSSELL", "team_name": "Mercedes"}
]

MOCK_POSITIONS = [
    {"date": "2026-07-05T14:00:00Z", "driver_number": 16, "position": 1},
    {"date": "2026-07-05T14:00:00Z", "driver_number": 63, "position": 2},
    {"date": "2026-07-05T15:30:00Z", "driver_number": 16, "position": 1},
    {"date": "2026-07-05T15:30:00Z", "driver_number": 63, "position": 2},
]

MOCK_LAPS = [
    {"driver_number": 16, "lap_number": 1, "lap_duration": 90.0},
    {"driver_number": 16, "lap_number": 2, "lap_duration": 85.0},
    {"driver_number": 63, "lap_number": 1, "lap_duration": 91.0},
    {"driver_number": 63, "lap_number": 2, "lap_duration": 86.0},
]

MOCK_SESSION_RACE = [{"session_key": 11326, "session_name": "Race", "session_type": "Race"}]
MOCK_SESSION_PRACTICE = [{"session_key": 11316, "session_name": "Practice 1", "session_type": "Practice"}]

@patch("ingestion.openf1_client.fetch_json_with_retry", new_callable=AsyncMock)
async def test_fetch_f1_session_times_race_total_time(mock_fetch):
    """Test that Race session returns total race time (sum of laps) even if session_name is Unknown initially."""
    def mock_fetch_side_effect(client, url, *args, **kwargs):
        if "/sessions" in url:
            return MOCK_SESSION_RACE
        elif "/drivers" in url:
            return MOCK_DRIVERS
        elif "/position" in url:
            return MOCK_POSITIONS
        elif "/laps" in url:
            return MOCK_LAPS
        return []

    mock_fetch.side_effect = mock_fetch_side_effect

    # Call with session_name="Unknown" (default)
    result = await fetch_f1_session_times(11326, 1289)

    assert result is not None
    assert len(result.standings) == 2

    # Driver 16: sum of 90.0 + 85.0 = 175.0s -> 02m 55.000s
    assert result.standings[0].driver_name == "Charles LECLERC"
    assert result.standings[0].time == "02m 55.000s"

    # Driver 63: sum of 91.0 + 86.0 = 177.0s -> 02m 57.000s
    assert result.standings[1].driver_name == "George RUSSELL"
    assert result.standings[1].time == "02m 57.000s"
    assert result.standings[1].diff_to_first == "+2.000s"


@patch("ingestion.openf1_client.fetch_json_with_retry", new_callable=AsyncMock)
async def test_fetch_f1_session_times_practice_fastest_lap(mock_fetch):
    """Test that Practice session returns fastest lap time (min of laps)."""
    def mock_fetch_side_effect(client, url, *args, **kwargs):
        if "/sessions" in url:
            return MOCK_SESSION_PRACTICE
        elif "/drivers" in url:
            return MOCK_DRIVERS
        elif "/position" in url:
            return MOCK_POSITIONS
        elif "/laps" in url:
            return MOCK_LAPS
        return []

    mock_fetch.side_effect = mock_fetch_side_effect

    result = await fetch_f1_session_times(11316, 1289, session_name="Practice 1")

    assert result is not None
    assert len(result.standings) == 2

    # Driver 16: min of 90.0 and 85.0 = 85.0s -> 01m 25.000s
    assert result.standings[0].driver_name == "Charles LECLERC"
    assert result.standings[0].time == "01m 25.000s"


@patch("ingestion.openf1_client.fetch_json_with_retry", new_callable=AsyncMock)
async def test_get_race_winner_returns_time(mock_fetch):
    """Test that get_race_winner_from_openf1 returns winner name, team, and total race time."""
    def mock_fetch_side_effect(client, url, *args, **kwargs):
        if "/position" in url:
            return [{"driver_number": 16, "date": "2026-07-05T15:30:00Z"}]
        elif "/drivers" in url:
            return [{"driver_number": 16, "full_name": "Charles LECLERC", "team_name": "Ferrari"}]
        elif "/laps" in url:
            return [
                {"driver_number": 16, "lap_duration": 90.0},
                {"driver_number": 16, "lap_duration": 85.0}
            ]
        return []

    mock_fetch.side_effect = mock_fetch_side_effect

    name, team, total_time = await get_race_winner_from_openf1(AsyncMock(), 11326)

    assert name == "Charles LECLERC"
    assert team == "Ferrari"
    assert total_time == "02m 55.000s"
