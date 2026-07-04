# extracts info from external wrc apis

import asyncio
from openwrc.clients.wrc_api_client import WrcApiClient
from openwrc.models.external_api import (
    ApiEntry,
    ApiEventMetadata,
    ApiSplitTimeResults,
    ApiStageResults,
    ApiStageTimeResults,
)


def get_rally_ids(event_metadata: ApiEventMetadata) -> list[int]:
    return [rally.rally_id for rally in event_metadata.rallies]


def get_rally_id_to_itinerary_id(event_metadata: ApiEventMetadata) -> dict[int, int]:
    return {rally.rally_id: rally.itinerary_id for rally in event_metadata.rallies}


async def get_rally_id_to_api_entries(
    client: WrcApiClient, event_id: int, rally_ids: list[int]
) -> dict[int, list[ApiEntry]]:
    composite_entries = await asyncio.gather(
        *[client.get_rally_entries(event_id=event_id, rally_id=id) for id in rally_ids]
    )
    flattened_entries = []
    for entries in composite_entries:
        flattened_entries.extend(entries)
    return flattened_entries


async def get_event_stage_results_with_context(
    client: WrcApiClient, event_id: int, rally_id: int, stage_id: int
) -> tuple[ApiStageResults, int, int]:
    results = await client.get_event_stage_results(
        event_id=event_id, rally_id=rally_id, stage_id=stage_id
    )
    return (results, rally_id, stage_id)


async def get_event_stage_split_times_with_context(
    client: WrcApiClient, event_id: int, rally_id: int, stage_id: int
) -> tuple[ApiSplitTimeResults, int, int]:
    results = await client.get_rally_stage_split_time_results(
        event_id=event_id, rally_id=rally_id, stage_id=stage_id
    )
    return (results, rally_id, stage_id)


async def get_event_stage_times_with_context(
    client: WrcApiClient, event_id: int, rally_id: int, stage_id: int
) -> tuple[ApiStageTimeResults, int, int]:
    results = await client.get_event_stage_time_results(
        event_id=event_id, rally_id=rally_id, stage_id=stage_id
    )
    return (results, rally_id, stage_id)
