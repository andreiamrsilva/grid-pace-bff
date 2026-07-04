"""
Unit tests for API to DB model mapper functions.
"""

import pytest
from datetime import datetime, date, timezone

from openwrc.storage.mappers import (
    map_api_event_to_db_model,
    map_api_rally_to_db_model,
    map_api_person_to_db_model,
    map_api_driver_to_db_model,
    map_api_codriver_to_db_model,
    map_api_entry_to_db_model,
    map_api_itinerary_to_db_model,
    map_api_itinerary_leg_to_db_model,
    map_api_itinerary_section_to_db_model,
    map_api_stage_to_db_model,
    map_api_control_to_db_model,
    map_api_start_list_to_db_model,
)
from openwrc.models.db.entities import PersonType
from openwrc.models.external_api import (
    ApiEventMetadata,
    ApiRallyMetadata,
    ApiCountryMetadata,
    ApiPerson,
    ApiDriver,
    ApiCoDriver,
    ApiEntry,
    ApiItinerary,
    ApiItineraryLeg,
    ApiItinerarySection,
    ApiStage,
    ApiControl,
    ApiStartList,
    ApiManufacturer,
    ApiEntrant,
    ApiGroup,
)


class TestEventMetadataMapper:
    """Tests for map_event_metadata_to_db_model"""

    def test_maps_all_fields_correctly(self):
        # Create minimal rally to satisfy constraint
        minimal_rally = ApiRallyMetadata(
            rally_id=456,
            event_id=123,
            itinerary_id=789,
            name="WRC1",
            is_main=True,
            event_classes=[],
        )

        api_event = ApiEventMetadata(
            event_id=123,
            name="Rally Monte Carlo",
            location="Monaco",
            slug="rally-monte-carlo",
            surfaces="Asphalt",
            start_date=datetime(2024, 1, 18, tzinfo=timezone.utc),
            finish_date=datetime(2024, 1, 21, tzinfo=timezone.utc),
            time_zone_id="Europe/Monaco",
            time_zone_name="CET",
            country_id=1,
            country=ApiCountryMetadata(
                country_id=1, name="Monaco", iso2="MC", iso3="MCO"
            ),
            shakedown_count=1,
            rallies=[minimal_rally],
            event_classes=[],
        )

        db_event = map_api_event_to_db_model(api_event)

        assert db_event.event_id == 123
        assert db_event.name == "Rally Monte Carlo"
        assert db_event.location == "Monaco"
        assert db_event.slug == "rally-monte-carlo"
        assert db_event.surfaces == "Asphalt"
        # Note: API model converts dates to UTC, so we test the converted values
        assert db_event.start_date == api_event.start_date
        assert db_event.finish_date == api_event.finish_date
        assert db_event.time_zone_id == "Europe/Monaco"
        assert db_event.time_zone_name == "CET"
        assert db_event.country_id == 1
        assert db_event.shakedown_count == 1

    def test_converts_timezone_id_to_string(self):
        # Create minimal rally to satisfy constraint
        minimal_rally = ApiRallyMetadata(
            rally_id=456,
            event_id=123,
            itinerary_id=789,
            name="WRC1",
            is_main=True,
            event_classes=[],
        )

        api_event = ApiEventMetadata(
            event_id=123,
            name="Test Event",
            location="Test",
            slug="test",
            surfaces="Gravel",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            finish_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
            time_zone_id="Europe/Paris",
            time_zone_name="CET",
            country_id=1,
            country=ApiCountryMetadata(
                country_id=1, name="France", iso2="FR", iso3="FRA"
            ),
            shakedown_count=0,
            rallies=[minimal_rally],
            event_classes=[],
        )

        db_event = map_api_event_to_db_model(api_event)

        assert isinstance(db_event.time_zone_id, str)
        assert db_event.time_zone_id == "Europe/Paris"


class TestRallyMetadataMapper:
    """Tests for map_rally_metadata_to_db_model"""

    def test_maps_all_fields_correctly(self):
        api_rally = ApiRallyMetadata(
            rally_id=456,
            event_id=123,
            itinerary_id=789,
            name="WRC1",
            is_main=True,
            event_classes=[],
        )

        db_rally = map_api_rally_to_db_model(api_rally)

        assert db_rally.rally_id == 456
        assert db_rally.event_id == 123
        assert db_rally.itinerary_id == 789
        assert db_rally.name == "WRC1"
        assert db_rally.is_main is True

    def test_handles_non_main_rally(self):
        api_rally = ApiRallyMetadata(
            rally_id=457,
            event_id=123,
            itinerary_id=790,
            name="WRC2",
            is_main=False,
            event_classes=[],
        )

        db_rally = map_api_rally_to_db_model(api_rally)

        assert db_rally.is_main is False


class TestPersonMappers:
    """Tests for person-related mappers"""

    def test_map_person_with_all_fields(self):
        api_person = ApiPerson(
            person_id=100,
            country_id=1,
            country=ApiCountryMetadata(
                country_id=1, name="France", iso2="FR", iso3="FRA"
            ),
            season_id=2024,
            event_id=None,
            external_id="ext-123",
            first_name="Sébastien",
            last_name="Ogier",
            abbv_name="S. OGIER",
            full_name="Sébastien Ogier",
            code="OGI",
            license_number="LIC123",
            state="active",
        )

        db_person = map_api_person_to_db_model(api_person, PersonType.PERSON)

        assert db_person.person_id == 100
        assert db_person.person_type == PersonType.PERSON
        assert db_person.country_id == 1
        assert db_person.season_id == 2024
        assert db_person.external_id == "ext-123"
        assert db_person.first_name == "Sébastien"
        assert db_person.last_name == "Ogier"
        assert db_person.abbv_name == "S. OGIER"
        assert db_person.full_name == "Sébastien Ogier"
        assert db_person.code == "OGI"
        assert db_person.license_number == "LIC123"
        assert db_person.state == "active"

    def test_map_driver_sets_correct_person_type(self):
        api_driver = ApiDriver(
            person_id=100,
            country_id=1,
            country=ApiCountryMetadata(
                country_id=1, name="France", iso2="FR", iso3="FRA"
            ),
            first_name="Sébastien",
            last_name="Ogier",
            abbv_name="S. OGIER",
            full_name="Sébastien Ogier",
            code="OGI",
        )

        db_driver = map_api_driver_to_db_model(api_driver)

        assert db_driver.person_type == PersonType.DRIVER
        assert db_driver.person_id == 100

    def test_map_codriver_sets_correct_person_type(self):
        api_codriver = ApiCoDriver(
            person_id=101,
            country_id=1,
            country=ApiCountryMetadata(
                country_id=1, name="France", iso2="FR", iso3="FRA"
            ),
            first_name="Vincent",
            last_name="Landais",
            abbv_name="V. LANDAIS",
            full_name="Vincent Landais",
            code="LAN",
        )

        db_codriver = map_api_codriver_to_db_model(api_codriver)

        assert db_codriver.person_type == PersonType.CODRIVER
        assert db_codriver.person_id == 101

    def test_handles_optional_fields_as_none(self):
        api_person = ApiPerson(
            person_id=102,
            country_id=1,
            country=ApiCountryMetadata(
                country_id=1, name="Test", iso2="TS", iso3="TST"
            ),
            season_id=None,
            event_id=None,
            external_id=None,
            first_name="Test",
            last_name="Driver",
            abbv_name="T. DRIVER",
            full_name="Test Driver",
            code="DRV",
            license_number=None,
            state=None,
        )

        db_person = map_api_person_to_db_model(api_person, PersonType.DRIVER)

        assert db_person.season_id is None
        assert db_person.external_id is None
        assert db_person.license_number is None
        assert db_person.state is None


class TestEntryMapper:
    """Tests for map_api_entry_to_db_model"""

    def test_maps_all_fields_correctly(self):
        # Create mock nested objects for Entry
        mock_driver = ApiDriver(
            person_id=100,
            country_id=1,
            country=ApiCountryMetadata(
                country_id=1, name="France", iso2="FR", iso3="FRA"
            ),
            first_name="Sébastien",
            last_name="Ogier",
            abbv_name="S. OGIER",
            full_name="Sébastien Ogier",
            code="OGI",
        )

        mock_codriver = ApiCoDriver(
            person_id=101,
            country_id=1,
            country=ApiCountryMetadata(
                country_id=1, name="France", iso2="FR", iso3="FRA"
            ),
            first_name="Vincent",
            last_name="Landais",
            abbv_name="V. LANDAIS",
            full_name="Vincent Landais",
            code="LAN",
        )

        mock_manufacturer = ApiManufacturer(
            manufacturer_id=1,
            name="Toyota Gazoo Racing WRT",
        )

        mock_entrant = ApiEntrant(
            entrant_id=1,
            name="Toyota Gazoo Racing WRT",
        )

        mock_group = ApiGroup(
            group_id=1,
            name="Rally1",
        )

        api_entry = ApiEntry(
            entry_id=500,
            event_id=123,
            driver=mock_driver,
            codriver=mock_codriver,
            manufacturer=mock_manufacturer,
            entrant=mock_entrant,
            group=mock_group,
            event_classes=[],
            driver_id=100,
            codriver_id=101,
            manufacturer_id=1,
            entrant_id=1,
            group_id=1,
            identifier="11",
            vehicle_model="GR Yaris Rally1",
            entry_list_order=1,
            eligibility="M",
            priority="P1",
            status="Entry",
            tyre_manufacturer="Pirelli",
        )

        db_entry = map_api_entry_to_db_model(api_entry)

        assert db_entry.entry_id == 500
        assert db_entry.event_id == 123
        assert db_entry.driver_id == 100
        assert db_entry.codriver_id == 101
        assert db_entry.manufacturer_id == 1
        assert db_entry.entrant_id == 1
        assert db_entry.group_id == 1
        assert db_entry.identifier == "11"
        assert db_entry.vehicle_model == "GR Yaris Rally1"
        assert db_entry.entry_list_order == 1
        assert db_entry.eligibility == "M"
        assert db_entry.priority == "P1"
        assert db_entry.status == "Entry"
        assert db_entry.tyre_manufacturer == "Pirelli"


class TestItineraryMappers:
    """Tests for itinerary-related mappers"""

    def test_map_itinerary(self):
        api_itinerary = ApiItinerary(
            itinerary_id=789,
            event_id=123,
            itinerary_legs=[],
        )

        db_itinerary = map_api_itinerary_to_db_model(api_itinerary)

        assert db_itinerary.itinerary_id == 789
        assert db_itinerary.event_id == 123

    def test_map_itinerary_leg(self):
        api_leg = ApiItineraryLeg(
            itinerary_leg_id=1001,
            itinerary_id=789,
            start_list_id=2001,
            name="Thursday",
            leg_date=date(2024, 1, 18),
            order=1,
            status="Scheduled",
            itinerary_sections=[],
        )

        db_leg = map_api_itinerary_leg_to_db_model(api_leg)

        assert db_leg.itinerary_leg_id == 1001
        assert db_leg.itinerary_id == 789
        assert db_leg.start_list_id == 2001
        assert db_leg.name == "Thursday"
        assert db_leg.leg_date == date(2024, 1, 18)
        assert db_leg.order == 1
        assert db_leg.status == "Scheduled"

    def test_map_itinerary_leg_with_null_start_list(self):
        api_leg = ApiItineraryLeg(
            itinerary_leg_id=1002,
            itinerary_id=789,
            start_list_id=None,
            name="Friday",
            leg_date=date(2024, 1, 19),
            order=2,
            status="Scheduled",
            itinerary_sections=[],
        )

        db_leg = map_api_itinerary_leg_to_db_model(api_leg)

        assert db_leg.start_list_id is None

    def test_map_itinerary_section(self):
        api_section = ApiItinerarySection(
            itinerary_section_id=3001,
            itinerary_leg_id=1001,
            name="Morning Loop",
            order=1,
            stages=[],
            controls=[],
        )

        db_section = map_api_itinerary_section_to_db_model(api_section)

        assert db_section.itinerary_section_id == 3001
        assert db_section.itinerary_leg_id == 1001
        assert db_section.name == "Morning Loop"
        assert db_section.order == 1

    def test_map_stage_with_itinerary_section_id(self):
        api_stage = ApiStage(
            stage_id=4001,
            event_id=123,
            number=1,
            name="SS1 Test Stage",
            distance=15.5,
            status="Scheduled",
            stage_type="StandardStage",
            timing_precision="Tenth",
            locked=False,
            code="SS1",
        )

        db_stage = map_api_stage_to_db_model(api_stage, itinerary_section_id=3001)

        assert db_stage.stage_id == 4001
        assert db_stage.event_id == 123
        assert db_stage.itinerary_section_id == 3001
        assert db_stage.number == 1
        assert db_stage.name == "SS1 Test Stage"
        assert db_stage.distance == 15.5
        assert db_stage.status == "Scheduled"
        assert db_stage.stage_type == "StandardStage"
        assert db_stage.timing_precision == "Tenth"
        assert db_stage.locked is False
        assert db_stage.code == "SS1"

    def test_map_control_with_itinerary_section_id(self):
        api_control = ApiControl(
            control_id=5001,
            event_id=123,
            stage_id=4001,
            type="TimeControl",
            code="TC1",
            location="Test Location",
            status="Scheduled",
            timing_precision="Minute",
            distance=10.0,
            target_duration_ms=600000,
            first_car_due_date_time=datetime(2024, 1, 18, 8, 0, tzinfo=timezone.utc),
            first_car_due_date_time_local=None,
            control_penalties="All",
            rounding_policy="RoundToClosestMinute",
            locked=False,
            bogey_ms=None,
        )

        db_control = map_api_control_to_db_model(api_control, itinerary_section_id=3001)

        assert db_control.control_id == 5001
        assert db_control.event_id == 123
        assert db_control.itinerary_section_id == 3001
        assert db_control.stage_id == 4001
        assert db_control.type == "TimeControl"
        assert db_control.code == "TC1"
        assert db_control.location == "Test Location"

    def test_map_start_list(self):
        api_start_list = ApiStartList(
            start_list_id=2001,
            event_id=123,
            name="Thursday Start List",
            published_status="Published",
            start_list_items=[],
        )

        db_start_list = map_api_start_list_to_db_model(api_start_list)

        assert db_start_list.start_list_id == 2001
        assert db_start_list.event_id == 123
        assert db_start_list.published_status == "Published"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
