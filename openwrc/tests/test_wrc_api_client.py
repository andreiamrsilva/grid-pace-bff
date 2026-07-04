"""
Integration tests for WrcApiClient
Tests all endpoints with real API calls to verify model validation works correctly
"""

import pytest
import pytest_asyncio
from openwrc.clients.wrc_api_client import WrcApiClient
from openwrc.models.external_api import (
    ApiEventMetadata,
    ApiItinerary,
    ApiStartList,
)


# Test data
EVENT_ID = 555
RALLY_ID = 603
STAGE_ID = 10279
ITINERARY_ID = 1343

SHAKEDOWN_EVENT_ID = 635
SHAKEDOWN_NUMBER = 1
START_LIST_ID = 2158


@pytest_asyncio.fixture
async def client() -> WrcApiClient:
    """Create a WrcApiClient instance (auto-closed)."""
    async with WrcApiClient() as c:
        yield c


@pytest.mark.asyncio
async def test_get_event_metadata(client: WrcApiClient) -> None:
    """Test fetching event metadata"""
    result = await client.get_event_metadata(EVENT_ID)

    assert isinstance(result, ApiEventMetadata)
    assert result.event_id == EVENT_ID
    assert len(result.rallies) > 0
    print(f"✓ Event metadata: {result.name}")


@pytest.mark.asyncio
async def test_get_event_itineraries(client: WrcApiClient) -> None:
    """Test fetching event itineraries"""
    result = await client.get_event_itineraries(EVENT_ID, ITINERARY_ID)

    assert isinstance(result, ApiItinerary)
    assert result.itinerary_id == ITINERARY_ID
    assert len(result.itinerary_legs) > 0
    print(f"✓ Itinerary: {len(result.itinerary_legs)} legs")


@pytest.mark.asyncio
async def test_get_rally_entries(client: WrcApiClient) -> None:
    """Test fetching rally entries"""
    result = await client.get_rally_entries(EVENT_ID, RALLY_ID)

    assert isinstance(result, list)
    assert len(result) > 0
    print(f"✓ Rally entries: {len(result)} entries")


@pytest.mark.asyncio
async def test_get_rally_results(client: WrcApiClient) -> None:
    """Test fetching rally results"""
    result = await client.get_rally_results(EVENT_ID, RALLY_ID)

    assert isinstance(result, list)
    assert len(result) > 0
    # Verify each entry has the required fields
    for entry in result:
        assert hasattr(entry, "entry_id")
        assert hasattr(entry, "stage_time_ms")
        assert hasattr(entry, "total_time_ms")
    print(f"✓ Rally results: {len(result)} entries")


@pytest.mark.asyncio
async def test_get_event_stage_results(client: WrcApiClient) -> None:
    """Test fetching stage results"""
    result = await client.get_event_stage_results(EVENT_ID, STAGE_ID, RALLY_ID)

    assert isinstance(result, list)
    assert len(result) > 0
    # Verify each entry has the required fields
    for entry in result:
        assert hasattr(entry, "entry_id")
        assert hasattr(entry, "stage_time_ms")
    print(f"✓ Stage results: {len(result)} entries")


@pytest.mark.asyncio
async def test_get_event_stage_time_results(client: WrcApiClient) -> None:
    """Test fetching stage time results"""
    result = await client.get_event_stage_time_results(EVENT_ID, STAGE_ID, RALLY_ID)

    assert isinstance(result, list)
    assert len(result) > 0
    # Verify each entry has the required fields
    for entry in result:
        assert hasattr(entry, "stage_id")
        assert hasattr(entry, "status")
        assert entry.stage_id == STAGE_ID
    print(f"✓ Stage time results: {len(result)} entries")


@pytest.mark.asyncio
async def test_get_event_shakedown_results(client: WrcApiClient) -> None:
    """Test fetching shakedown results"""
    result = await client.get_event_shakedown_results(
        SHAKEDOWN_EVENT_ID, SHAKEDOWN_NUMBER
    )

    assert isinstance(result, list)
    assert len(result) > 0
    # Verify each entry has the required fields
    for entry in result:
        assert hasattr(entry, "shakedown_time_id")
        assert hasattr(entry, "entry_id")
        assert hasattr(entry, "run_duration_ms")
        assert entry.shakedown_number == SHAKEDOWN_NUMBER
    print(f"✓ Shakedown results: {len(result)} entries")


@pytest.mark.asyncio
async def test_get_event_start_list(client: WrcApiClient) -> None:
    """Test fetching start list"""
    result = await client.get_event_start_list(SHAKEDOWN_EVENT_ID, START_LIST_ID)

    assert isinstance(result, ApiStartList)
    assert result.start_list_id == START_LIST_ID
    assert len(result.start_list_items) > 0
    # Verify each item has the required fields
    for item in result.start_list_items:
        assert hasattr(item, "start_list_item_id")
        assert hasattr(item, "entry_id")
        assert hasattr(item, "order")
        assert hasattr(item, "start_date_time")
    print(f"✓ Start list: {len(result.start_list_items)} entries")


@pytest.mark.asyncio
async def test_all_endpoints_integration(client: WrcApiClient) -> None:
    """Integration test that exercises all endpoints in sequence"""
    print("\n=== Running full integration test ===")

    # 1. Get event metadata
    event = await client.get_event_metadata(EVENT_ID)
    print(f"1. Event: {event.name} ({event.event_id})")

    # 2. Get itinerary
    itinerary = await client.get_event_itineraries(EVENT_ID, ITINERARY_ID)
    print(f"2. Itinerary: {len(itinerary.itinerary_legs)} legs")

    # 3. Get rally entries
    entries = await client.get_rally_entries(EVENT_ID, RALLY_ID)
    print(f"3. Entries: {len(entries)} drivers")

    # 4. Get rally results
    rally_results = await client.get_rally_results(EVENT_ID, RALLY_ID)
    print(f"4. Rally results: {len(rally_results)} entries")

    # 5. Get stage results
    stage_results = await client.get_event_stage_results(EVENT_ID, STAGE_ID, RALLY_ID)
    print(f"5. Stage results: {len(stage_results)} entries")

    # 6. Get stage time results
    stage_times = await client.get_event_stage_time_results(
        EVENT_ID, STAGE_ID, RALLY_ID
    )
    print(f"6. Stage time results: {len(stage_times)} entries")

    print("=== All endpoints working correctly ===\n")
