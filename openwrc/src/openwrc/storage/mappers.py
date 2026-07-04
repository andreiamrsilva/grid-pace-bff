from datetime import datetime, timezone

from openwrc.models.db.entities import CoDriver, Driver, Person, PersonType
from openwrc.models.db.event import (
    Entry,
    EventMetadata,
    EventMetadataDetails,
    RallyMetadata,
    Season,
)
from openwrc.models.db.itinerary import (
    Control,
    Itinerary,
    ItineraryLeg,
    ItinerarySection,
    Stage,
    StartList,
)
from openwrc.models.db.result import RallyStanding, SplitTime, StageTime
from openwrc.models.external_api import (
    ApiDriver,
    ApiCoDriver,
    ApiEntry,
    ApiEventMetadata,
    ApiItinerary,
    ApiItineraryLeg,
    ApiItinerarySection,
    ApiPerson,
    ApiRallyMetadata,
    ApiResultEntry,
    ApiSeason,
    ApiSeasonRound,
    ApiSplitTimeEntry,
    ApiStage,
    ApiControl,
    ApiStageTimeEntry,
    ApiStartList,
)


def map_api_season_to_db_model(api_season: ApiSeason) -> Season:
    return Season(
        season_id=api_season.season_id,
        name=api_season.name,
        year=api_season.year,
    )


def map_api_event_metadata_to_details(api: ApiEventMetadata) -> EventMetadataDetails:
    return EventMetadataDetails(
        name=api.name,
        location=api.location,
        slug=api.slug,
        surfaces=api.surfaces,
        start_date=api.start_date,
        finish_date=api.finish_date,
        time_zone_id=str(api.time_zone_id),
        time_zone_name=api.time_zone_name,
        country_id=api.country_id,
        shakedown_count=api.shakedown_count,
    )


def map_api_season_round_to_event_db_model(round: ApiSeasonRound) -> EventMetadata:
    e = round.event
    # season-detail dates are date-only (no time); store as midnight UTC
    start_dt = datetime(
        e.start_date.year, e.start_date.month, e.start_date.day, tzinfo=timezone.utc
    )
    finish_dt = datetime(
        e.finish_date.year, e.finish_date.month, e.finish_date.day, tzinfo=timezone.utc
    )
    return EventMetadata(
        event_id=e.event_id,
        season_id=round.season_id,
        round_order=round.order,
        name=e.name,
        location=e.location,
        slug=e.slug,
        surfaces=e.surfaces,
        start_date=start_dt,
        finish_date=finish_dt,
        time_zone_id=e.time_zone_id,
        time_zone_name=e.time_zone_name,
        country_id=e.country.country_id,
        shakedown_count=e.shakedown_count,
    )


def map_api_rally_to_db_model(api_rally: ApiRallyMetadata) -> RallyMetadata:
    return RallyMetadata(
        rally_id=api_rally.rally_id,
        event_id=api_rally.event_id,
        itinerary_id=api_rally.itinerary_id,
        name=api_rally.name,
        is_main=api_rally.is_main,
    )


def map_api_person_to_db_model(
    api_person: ApiPerson, person_type: PersonType
) -> Person:
    return Person(
        person_id=api_person.person_id,
        person_type=person_type,
        country_id=api_person.country_id,
        season_id=api_person.season_id,
        external_id=api_person.external_id,
        first_name=api_person.first_name,
        last_name=api_person.last_name,
        abbv_name=api_person.abbv_name,
        full_name=api_person.full_name,
        code=api_person.code,
        license_number=api_person.license_number,
        state=api_person.state,
    )


def map_api_driver_to_db_model(api_driver: ApiDriver) -> Driver:
    return map_api_person_to_db_model(
        api_person=api_driver, person_type=PersonType.DRIVER
    )


def map_api_codriver_to_db_model(api_codriver: ApiCoDriver) -> CoDriver:
    return map_api_person_to_db_model(
        api_person=api_codriver, person_type=PersonType.CODRIVER
    )


def map_api_entry_to_db_model(api_entry: ApiEntry, rally_id: int) -> Entry:
    return Entry(
        entry_id=api_entry.entry_id,
        rally_id=rally_id,
        driver_id=api_entry.driver_id,
        codriver_id=api_entry.codriver_id,
        manufacturer_id=api_entry.manufacturer_id,
        entrant_id=api_entry.entrant_id,
        group_id=api_entry.group_id,
        identifier=api_entry.identifier,
        vehicle_model=api_entry.vehicle_model,
        entry_list_order=api_entry.entry_list_order,
        eligibility=api_entry.eligibility,
        priority=api_entry.priority,
        status=api_entry.status,
        tyre_manufacturer=api_entry.tyre_manufacturer,
        pbf=api_entry.pbf,
        drive=api_entry.drive,
        tags=api_entry.tags,
    )


def map_api_itinerary_to_db_model(
    api_itinerary: ApiItinerary, rally_id: int
) -> Itinerary:
    return Itinerary(
        itinerary_id=api_itinerary.itinerary_id,
        event_id=api_itinerary.event_id,
        rally_id=rally_id,
    )


def map_api_itinerary_leg_to_db_model(
    api_itinerary_leg: ApiItineraryLeg,
) -> ItineraryLeg:
    return ItineraryLeg(
        itinerary_leg_id=api_itinerary_leg.itinerary_leg_id,
        itinerary_id=api_itinerary_leg.itinerary_id,
        start_list_id=api_itinerary_leg.start_list_id,
        name=api_itinerary_leg.name,
        leg_date=api_itinerary_leg.leg_date,
        order=api_itinerary_leg.order,
        status=api_itinerary_leg.status,
    )


def map_api_itinerary_section_to_db_model(
    api_itinerary_section: ApiItinerarySection,
) -> ItinerarySection:
    return ItinerarySection(
        itinerary_section_id=api_itinerary_section.itinerary_section_id,
        itinerary_leg_id=api_itinerary_section.itinerary_leg_id,
        name=api_itinerary_section.name,
        order=api_itinerary_section.order,
    )


def map_api_stage_to_db_model(api_stage: ApiStage, itinerary_section_id: int) -> Stage:
    return Stage(
        itinerary_section_id=itinerary_section_id,
        **api_stage.model_dump(),
    )


def map_api_control_to_db_model(
    api_control: ApiControl, itinerary_section_id: int
) -> Control:
    return Control(
        itinerary_section_id=itinerary_section_id, **api_control.model_dump()
    )


def map_api_start_list_to_db_model(api_start_list: ApiStartList) -> StartList:
    return StartList(
        start_list_id=api_start_list.start_list_id,
        event_id=api_start_list.event_id,
        published_status=api_start_list.published_status,
        name=api_start_list.name,
    )


def map_api_stage_result_to_db_model(
    api_stage_result: ApiResultEntry, rally_id: int, stage_id: int
) -> RallyStanding:
    return RallyStanding(
        rally_id=rally_id,
        stage_id=stage_id,
        entry_id=api_stage_result.entry_id,
        position=api_stage_result.position,
        stage_time_ms=api_stage_result.stage_time_ms,
        penalty_time_ms=api_stage_result.penalty_time_ms,
        total_time_ms=api_stage_result.total_time_ms,
        diff_first_ms=api_stage_result.diff_first_ms,
        diff_prev_ms=api_stage_result.diff_prev_ms,
    )


def map_api_stage_time_to_db_model(
    api_stage_time: ApiStageTimeEntry, rally_id: int
) -> StageTime:
    return StageTime(
        stage_id=api_stage_time.stage_id,
        entry_id=api_stage_time.entry_id,
        rally_id=rally_id,
        elapsed_duration_ms=api_stage_time.elapsed_duration_ms,
        position=api_stage_time.position,
        diff_first_ms=api_stage_time.diff_first_ms,
        diff_prev_ms=api_stage_time.diff_prev_ms,
        status=api_stage_time.status,
        source=api_stage_time.source,
    )


def map_api_split_time_to_db_model(
    api_split_time: ApiSplitTimeEntry, stage_id: int, rally_id: int
) -> SplitTime:
    return SplitTime(
        split_point_time_id=api_split_time.split_point_time_id,
        split_point_id=api_split_time.split_point_id,
        rally_id=rally_id,
        stage_id=stage_id,
        entry_id=api_split_time.entry_id,
        start_date_time=api_split_time.start_date_time,
        split_date_time=api_split_time.split_date_time,
        elapsed_duration_ms=api_split_time.elapsed_duration_ms,
    )
