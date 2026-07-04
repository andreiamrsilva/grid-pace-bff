"""
CRUD utilities for storing WRC data models.
Stateless helper functions that transform API models to DB models and store them.
"""

from typing import TypeVar, Type
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from openwrc.models.db.base import Base
from openwrc.models.db.entities import Country, Entrant, Group, Manufacturer
from openwrc.models.db.event import (
    EntryEventClass,
    EventClass,
    EventMetadata,
    RallyEventClass,
)
from openwrc.models.db.itinerary import StartList, StartListPublishStatus
from openwrc.models.external_api import (
    ApiCoDriver,
    ApiControl,
    ApiCountryMetadata,
    ApiDriver,
    ApiEntrant,
    ApiEventClass,
    ApiEventMetadata,
    ApiGroup,
    ApiItinerary,
    ApiItineraryLeg,
    ApiItinerarySection,
    ApiManufacturer,
    ApiRallyEntries,
    ApiRallyMetadata,
    ApiSeason,
    ApiSeasonRound,
    ApiShakedownTimeResults,
    ApiSplitTimeResults,
    ApiStage,
    ApiStageResults,
    ApiStageTimeResults,
    ApiStartList,
)
from openwrc.models.external_api.base_external_model import WrcExternalApiBaseModel
from openwrc.storage.mappers import (
    map_api_codriver_to_db_model,
    map_api_control_to_db_model,
    map_api_driver_to_db_model,
    map_api_entry_to_db_model,
    map_api_event_metadata_to_details,
    map_api_itinerary_leg_to_db_model,
    map_api_itinerary_section_to_db_model,
    map_api_itinerary_to_db_model,
    map_api_rally_to_db_model,
    map_api_season_round_to_event_db_model,
    map_api_season_to_db_model,
    map_api_split_time_to_db_model,
    map_api_stage_result_to_db_model,
    map_api_stage_time_to_db_model,
    map_api_stage_to_db_model,
)


T = TypeVar("T", bound=Base)
ApiT = TypeVar("ApiT", bound=WrcExternalApiBaseModel)


async def upsert_instance(session: AsyncSession, instance: T) -> T:
    """
    Generic upsert helper.
    Updates if exists, inserts if not.
    """
    return await session.merge(instance=instance)


async def upsert_from_api(
    session: AsyncSession,
    api_model: ApiT,
    db_model_class: Type[T],
    exclude: set[str] | None = None,
) -> T:
    """
    Dumb wrapper: converts API model to DB model via model_dump and upserts.
    Use exact API object; errors will surface missing or mismatched fields.
    """
    data = api_model.model_dump(exclude=exclude)
    return await upsert_instance(session=session, instance=db_model_class(**data))


# upsert utils


# section Entities
async def upsert_countries(
    session: AsyncSession, api_response: list[ApiCountryMetadata]
):
    for country in api_response:
        await upsert_from_api(
            session=session, api_model=country, db_model_class=Country
        )


async def upsert_drivers(session: AsyncSession, api_response: list[ApiDriver]):
    for driver in api_response:
        await upsert_instance(
            session=session, instance=map_api_driver_to_db_model(driver)
        )


async def upsert_codrivers(session: AsyncSession, api_response: list[ApiCoDriver]):
    for co_driver in api_response:
        await upsert_instance(
            session=session,
            instance=map_api_codriver_to_db_model(api_codriver=co_driver),
        )


async def upsert_manufacturers(
    session: AsyncSession, api_response: list[ApiManufacturer]
):
    for manufacturer in api_response:
        await upsert_from_api(
            session=session, api_model=manufacturer, db_model_class=Manufacturer
        )


async def upsert_groups(session: AsyncSession, api_response: list[ApiGroup]):
    for group in api_response:
        await upsert_from_api(session=session, api_model=group, db_model_class=Group)


async def upsert_entrants(session: AsyncSession, api_response: list[ApiEntrant]):
    for entrant in api_response:
        await upsert_from_api(
            session=session, api_model=entrant, db_model_class=Entrant
        )


async def upsert_season(session: AsyncSession, api_season: ApiSeason) -> None:
    await upsert_instance(
        session=session, instance=map_api_season_to_db_model(api_season)
    )


async def upsert_event_from_catalog_round(
    session: AsyncSession, round: ApiSeasonRound
) -> None:
    await upsert_instance(
        session=session, instance=map_api_season_round_to_event_db_model(round)
    )


async def upsert_event_metadata_details(
    session: AsyncSession, event_id: int, event_metadata: ApiEventMetadata
) -> None:
    await session.execute(
        update(EventMetadata)
        .where(EventMetadata.event_id == event_id)
        .values(**map_api_event_metadata_to_details(event_metadata))
    )


# section ApiEventMetadata
async def upsert_event_classes(
    session: AsyncSession, api_response: list[ApiEventClass]
):
    for event_class in api_response:
        await upsert_from_api(
            session=session, api_model=event_class, db_model_class=EventClass
        )


async def upsert_rally_event_classes(
    session: AsyncSession, event_class_ids: list[int], rally_id: int
):
    for event_class_id in event_class_ids:
        await upsert_instance(
            session=session,
            instance=RallyEventClass(
                rally_id=rally_id,
                event_class_id=event_class_id,
            ),
        )


async def upsert_rally_metadata(
    session: AsyncSession, api_response: list[ApiRallyMetadata]
):
    for rally in api_response:
        await upsert_instance(
            session=session, instance=map_api_rally_to_db_model(rally)
        )


# section itinerary


async def upsert_event_itinerary(
    session: AsyncSession, api_response: ApiItinerary, rally_id: int
):
    # start with parent itinerary object
    itinerary = map_api_itinerary_to_db_model(
        api_itinerary=api_response, rally_id=rally_id
    )
    await upsert_instance(session=session, instance=itinerary)


async def upsert_itinerary_legs(
    session: AsyncSession, api_response: list[ApiItineraryLeg], event_id: int
):
    async def try_upsert_leg(leg: ApiItineraryLeg):
        """_summary_

        Args:
            leg (ApiItineraryLeg): if the start list of the leg is not yet available, insert the start list with published status to '
        """
        start_list = await session.get(StartList, leg.start_list_id)
        if not start_list:
            # try inserting an unpublished start list
            await upsert_instance(
                session=session,
                instance=StartList(
                    start_list_id=leg.start_list_id,
                    event_id=event_id,
                    name="",
                    published_status=StartListPublishStatus.UNPUBLISHED,
                ),
            )
        await upsert_instance(
            session=session, instance=map_api_itinerary_leg_to_db_model(leg)
        )

    for leg in api_response:
        await try_upsert_leg(leg=leg)


async def upsert_itinerary_sections(
    session: AsyncSession, api_response: list[ApiItinerarySection]
):
    for section in api_response:
        await upsert_instance(
            session=session,
            instance=map_api_itinerary_section_to_db_model(
                api_itinerary_section=section
            ),
        )


async def upsert_controls(
    session: AsyncSession, api_response: list[ApiControl], itinerary_section_id: int
):
    for control in api_response:
        await upsert_instance(
            session=session,
            instance=map_api_control_to_db_model(
                api_control=control,
                itinerary_section_id=itinerary_section_id,
            ),
        )


async def upsert_stages(
    session: AsyncSession, api_response: list[ApiStage], itinerary_section_id: int
):
    for stage in api_response:
        await upsert_instance(
            session=session,
            instance=map_api_stage_to_db_model(
                api_stage=stage,
                itinerary_section_id=itinerary_section_id,
            ),
        )


# section entries
async def upsert_entry_event_classes(
    session: AsyncSession, event_class_ids: list[int], entry_id: int
):
    for event_class_id in event_class_ids:
        await upsert_instance(
            session=session,
            instance=EntryEventClass(
                entry_id=entry_id,
                event_class_id=event_class_id,
            ),
        )


async def upsert_entries(
    session: AsyncSession, api_response: ApiRallyEntries, rally_id: int
):
    for entry in api_response:
        await upsert_instance(
            session=session,
            instance=map_api_entry_to_db_model(rally_id=rally_id, api_entry=entry),
        )


# start list section TODO


async def upsert_start_list(session: AsyncSession, api_response: ApiStartList):
    # TODO
    pass


# results section TODO
async def upsert_stage_results(
    session: AsyncSession, api_response: ApiStageResults, rally_id: int, stage_id: int
):
    for stage_result in api_response:
        await upsert_instance(
            session=session,
            instance=map_api_stage_result_to_db_model(
                api_stage_result=stage_result, rally_id=rally_id, stage_id=stage_id
            ),
        )


async def upsert_stage_time_results(
    session: AsyncSession, api_response: ApiStageTimeResults, rally_id: int
):
    for stage_time in api_response:
        await upsert_instance(
            session=session,
            instance=map_api_stage_time_to_db_model(
                api_stage_time=stage_time,
                rally_id=rally_id,
            ),
        )


async def upsert_split_time_results(
    session: AsyncSession,
    api_response: ApiSplitTimeResults,
    stage_id: int,
    rally_id: int,
):
    for split_time in api_response:
        await upsert_instance(
            session=session,
            instance=map_api_split_time_to_db_model(
                api_split_time=split_time, stage_id=stage_id, rally_id=rally_id
            ),
        )


def upsert_shakedown_results(
    session: AsyncSession, api_response: ApiShakedownTimeResults
):
    pass
