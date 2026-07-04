"""
Integration tests for WrcDataStore ETL functions.
Uses real API JSON fixtures from scripts/api_test_outputs/.
"""

import json
import os
import pytest
import pytest_asyncio

from openwrc.models.external_api import ApiEventMetadata, ApiEntry
from openwrc.storage.data_store_service import WrcDataStore


FIXTURES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "api_test_outputs"
)


def load_event_metadata() -> ApiEventMetadata:
    with open(os.path.join(FIXTURES_DIR, "event_metadata.json")) as f:
        return ApiEventMetadata(**json.load(f))


def load_rally_entries() -> list[ApiEntry]:
    with open(os.path.join(FIXTURES_DIR, "rally_entries.json")) as f:
        return [ApiEntry(**entry) for entry in json.load(f)]


@pytest_asyncio.fixture
async def store(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = WrcDataStore(db_path=db_path)
    await store.init_db()
    yield store
    await store.engine.dispose()


@pytest.mark.asyncio
async def test_etl_event_metadata(store):
    event_metadata = load_event_metadata()
    await store.etl_event_metadata(event_metadata)

    # verify data was written by reading it back
    from sqlalchemy import text

    async with store.SessionLocal() as session:
        # check event
        result = await session.execute(
            text("SELECT * FROM events WHERE event_id = 635")
        )
        event = result.fetchone()
        assert event is not None
        assert event.name == "Rallye Monte Carlo"

        # check rally
        result = await session.execute(
            text("SELECT * FROM rallies WHERE rally_id = 703")
        )
        rally = result.fetchone()
        assert rally is not None
        assert rally.event_id == 635

        # check event classes
        result = await session.execute(
            text("SELECT COUNT(*) FROM event_classes WHERE event_id = 635")
        )
        count = result.scalar()
        assert count == 6  # RC1, RC2, RC3, RC4, RC5, RGT

        # check rally-to-event-class mappings
        result = await session.execute(
            text("SELECT COUNT(*) FROM rally_event_classes WHERE rally_id = 703")
        )
        count = result.scalar()
        assert count == 6


@pytest.mark.asyncio
async def test_etl_event_entries(store):
    # need event metadata first for FK dependencies
    event_metadata = load_event_metadata()
    await store.etl_event_metadata(event_metadata)

    entries = load_rally_entries()
    await store.etl_event_entries(entries, rally_id=703)

    from sqlalchemy import text

    async with store.SessionLocal() as session:
        # check countries were upserted
        result = await session.execute(text("SELECT COUNT(*) FROM countries"))
        count = result.scalar()
        assert count > 0

        # check manufacturers
        result = await session.execute(
            text("SELECT * FROM manufacturers WHERE manufacturer_id = 84")
        )
        manu = result.fetchone()
        assert manu is not None
        assert manu.name == "Toyota"

        # check a driver (Person table)
        result = await session.execute(
            text("SELECT * FROM persons WHERE person_id = 21334")
        )
        driver = result.fetchone()
        assert driver is not None
        assert driver.last_name == "OGIER"

        # check a codriver
        result = await session.execute(
            text("SELECT * FROM persons WHERE person_id = 21335")
        )
        codriver = result.fetchone()
        assert codriver is not None
        assert codriver.last_name == "LANDAIS"

        # check entrants
        result = await session.execute(
            text("SELECT * FROM entrants WHERE entrant_id = 91")
        )
        entrant = result.fetchone()
        assert entrant is not None
        assert entrant.name == "TOYOTA GAZOO RACING WRT"

        # check groups
        result = await session.execute(
            text("SELECT * FROM groups WHERE group_id = 152")
        )
        group = result.fetchone()
        assert group is not None
        assert group.name == "Rally1"


@pytest.mark.asyncio
async def test_etl_event_info_integration(tmp_path):
    """Integration test that calls the real WRC API and runs the full ETL pipeline."""
    db_path = str(tmp_path / "integration_test.db")
    store = WrcDataStore(db_path=db_path)
    await store.init_db()

    try:
        await store.etl_event_info(event_id=635)

        from sqlalchemy import text

        async with store.SessionLocal() as session:
            # event metadata
            result = await session.execute(
                text("SELECT * FROM events WHERE event_id = 635")
            )
            event = result.fetchone()
            assert event is not None
            assert event.name == "Rallye Monte Carlo"

            # rallies
            result = await session.execute(
                text("SELECT COUNT(*) FROM rallies WHERE event_id = 635")
            )
            assert result.scalar() >= 1

            # itineraries
            result = await session.execute(text("SELECT COUNT(*) FROM itineraries"))
            assert result.scalar() >= 1

            # stages
            result = await session.execute(text("SELECT COUNT(*) FROM stages"))
            assert result.scalar() > 0

            # controls
            result = await session.execute(text("SELECT COUNT(*) FROM controls"))
            assert result.scalar() > 0

            # entries
            result = await session.execute(text("SELECT COUNT(*) FROM entries"))
            assert result.scalar() > 0

            # persons (drivers + codrivers)
            result = await session.execute(text("SELECT COUNT(*) FROM persons"))
            assert result.scalar() > 0

            # countries
            result = await session.execute(text("SELECT COUNT(*) FROM countries"))
            assert result.scalar() > 0

    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_etl_event_timings(tmp_path):
    """Integration test for etl_event_timings - populates rally_standings from stage results."""
    db_path = str(tmp_path / "etl_timings_test.db")
    store = WrcDataStore(db_path=db_path)
    await store.init_db()

    try:
        event_id = 635
        await store.etl_event_info(event_id=event_id)
        await store.etl_event_timings(event_id=event_id)

        from sqlalchemy import text

        async with store.SessionLocal() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM rally_standings"))
            count = result.scalar()
            assert count > 0

    finally:
        await store.engine.dispose()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
