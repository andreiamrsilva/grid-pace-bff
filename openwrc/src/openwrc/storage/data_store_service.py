"""
ETL service: fetches data from the WRC API and writes it to the local DB.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from openwrc.clients.wrc_api_client import WrcApiClient
from openwrc.models.db.event import RallyMetadata
from openwrc.models.db.itinerary import Stage
from openwrc.models.db.logs import EtlRunLog, EtlType
from openwrc.models.external_api import (
    ApiEventMetadata,
    ApiItinerary,
    ApiRallyEntries,
)
from openwrc.storage.database import WrcDatabase
from openwrc.storage.extract_utils import (
    get_event_stage_results_with_context,
    get_event_stage_split_times_with_context,
    get_event_stage_times_with_context,
    get_rally_id_to_itinerary_id,
    get_rally_ids,
)
from openwrc.storage.load_utils import (
    upsert_codrivers,
    upsert_controls,
    upsert_countries,
    upsert_drivers,
    upsert_entrants,
    upsert_entries,
    upsert_entry_event_classes,
    upsert_event_classes,
    upsert_event_from_catalog_round,
    upsert_event_itinerary,
    upsert_event_metadata_details,
    upsert_groups,
    upsert_itinerary_legs,
    upsert_itinerary_sections,
    upsert_manufacturers,
    upsert_rally_event_classes,
    upsert_rally_metadata,
    upsert_season,
    upsert_split_time_results,
    upsert_stage_results,
    upsert_stage_time_results,
    upsert_stages,
)
from openwrc.storage.transform_utils import (
    transform_api_entries,
    transform_api_event_metadata,
    transform_api_itinerary,
)


class WrcEtlService:

    def __init__(
        self,
        db: WrcDatabase | None = None,
        api_client: WrcApiClient | None = None,
    ) -> None:
        self._db = db or WrcDatabase()
        self._api = api_client or WrcApiClient()

    @asynccontextmanager
    async def _etl_run(
        self,
        etl_type: EtlType,
        event_id: int | None = None,
        ttl: timedelta | None = None,
    ):
        """
        Context manager that bookends an ETL function with run log entries.
        Records started_at before yielding and writes a completed EtlRunLog row
        on success. Exceptions propagate normally — no log entry is written on failure.
        ttl is converted to expires_at = now() + ttl; None means data never expires.
        """
        started_at = datetime.now(timezone.utc)
        yield
        completed_at = datetime.now(timezone.utc)
        expires_at = (completed_at + ttl) if ttl is not None else None
        async with self._db.session() as log_session:
            log_session.add(
                EtlRunLog(
                    event_id=event_id,
                    etl_type=etl_type.value,
                    started_at=started_at,
                    completed_at=completed_at,
                    expires_at=expires_at,
                )
            )
            await log_session.commit()

    async def etl_season_catalog(
        self,
        championship: str = "World Rally Championship",
        ttl: timedelta | None = None,
    ) -> None:
        """
        Populate Season and EventMetadata (catalog-level fields only) for all seasons
        matching the given championship name. Run this before etl_historical_event.
        """
        async with self._etl_run(EtlType.CATALOG, ttl=ttl):
            seasons = await self._api.get_seasons()
            wrc_seasons = [s for s in seasons if s.name == championship]

            for season in wrc_seasons:
                async with self._db.session() as session:
                    await upsert_season(session=session, api_season=season)
                    await session.commit()

                detail = await self._api.get_season_detail(season_id=season.season_id)
                async with self._db.session() as session:
                    for round in detail.season_rounds:
                        await upsert_event_from_catalog_round(
                            session=session, round=round
                        )
                    await session.commit()

    async def etl_historical_event(self, event_id: int) -> None:
        await self.etl_event_info(event_id=event_id)
        await self.etl_event_timings(event_id=event_id)

    async def etl_event_info(self, event_id: int, ttl: timedelta | None = None) -> None:
        event_metadata = await self._api.get_event_metadata(event_id=event_id)
        await self.etl_event_metadata(event_metadata=event_metadata, ttl=ttl)

        rally_ids = get_rally_ids(event_metadata=event_metadata)
        rally_ids_to_itinerary_ids = get_rally_id_to_itinerary_id(
            event_metadata=event_metadata
        )

        for rally_id, itinerary_id in rally_ids_to_itinerary_ids.items():
            itinerary = await self._api.get_event_itineraries(
                event_id=event_id, itinerary_id=itinerary_id
            )
            await self.etl_itinerary(itinerary=itinerary, rally_id=rally_id, ttl=ttl)

        for rally_id in rally_ids:
            entries = await self._api.get_rally_entries(
                event_id=event_id, rally_id=rally_id
            )
            await self.etl_event_entries(
                api_entries=entries, rally_id=rally_id, ttl=ttl
            )

    async def etl_itinerary(
        self, itinerary: ApiItinerary, rally_id: int, ttl: timedelta | None = None
    ) -> None:
        async with self._etl_run(
            EtlType.ITINERARY, event_id=itinerary.event_id, ttl=ttl
        ):
            legs, sections, section_id_to_controls, section_id_to_stages = (
                transform_api_itinerary(api_response=itinerary)
            )
            async with self._db.session() as session:
                await upsert_event_itinerary(
                    session=session, api_response=itinerary, rally_id=rally_id
                )
                await upsert_itinerary_legs(
                    session=session, api_response=legs, event_id=itinerary.event_id
                )
                await upsert_itinerary_sections(session=session, api_response=sections)
                for section_id, controls in section_id_to_controls.items():
                    await upsert_controls(
                        session=session,
                        api_response=controls,
                        itinerary_section_id=section_id,
                    )
                for section_id, stages in section_id_to_stages.items():
                    await upsert_stages(
                        session=session,
                        api_response=stages,
                        itinerary_section_id=section_id,
                    )
                await session.commit()

    async def etl_event_metadata(
        self, event_metadata: ApiEventMetadata, ttl: timedelta | None = None
    ) -> None:
        async with self._etl_run(
            EtlType.EVENT_METADATA, event_id=event_metadata.event_id, ttl=ttl
        ):
            rallies, event_classes, rally_to_class_ids = transform_api_event_metadata(
                api_response=event_metadata
            )
            async with self._db.session() as session:
                await upsert_event_metadata_details(
                    session=session,
                    event_id=event_metadata.event_id,
                    event_metadata=event_metadata,
                )
                await upsert_rally_metadata(session=session, api_response=rallies)
                await upsert_event_classes(session=session, api_response=event_classes)
                for rally_id, class_ids in rally_to_class_ids.items():
                    await upsert_rally_event_classes(
                        session=session, event_class_ids=class_ids, rally_id=rally_id
                    )
                await session.commit()

    async def etl_event_entries(
        self, api_entries: ApiRallyEntries, rally_id: int, ttl: timedelta | None = None
    ) -> None:
        async with self._etl_run(
            EtlType.ENTRIES, event_id=api_entries[0].event_id, ttl=ttl
        ):
            (
                countries,
                manufacturers,
                entrants,
                groups,
                drivers,
                codrivers,
                event_classes,
                entry_id_to_event_class_ids,
            ) = transform_api_entries(api_response=api_entries)
            async with self._db.session() as session:
                await upsert_countries(session=session, api_response=countries)
                await upsert_manufacturers(session=session, api_response=manufacturers)
                await upsert_entrants(session=session, api_response=entrants)
                await upsert_groups(session=session, api_response=groups)
                await upsert_drivers(session=session, api_response=drivers)
                await upsert_codrivers(session=session, api_response=codrivers)
                await upsert_event_classes(session=session, api_response=event_classes)
                for entry_id, class_ids in entry_id_to_event_class_ids.items():
                    await upsert_entry_event_classes(
                        session=session, event_class_ids=class_ids, entry_id=entry_id
                    )
                await upsert_entries(
                    session=session, api_response=api_entries, rally_id=rally_id
                )
                await session.commit()

    async def etl_event_timings(
        self, event_id: int, ttl: timedelta | None = None
    ) -> None:
        event_stages = await self._get_event_stages(event_id=event_id)
        event_stage_ids = [stage.stage_id for stage in event_stages]
        event_rallies = await self._get_event_rallies(event_id=event_id)
        rally_ids = [rally.rally_id for rally in event_rallies]

        await self.etl_event_rally_stage_results(
            event_id=event_id, stage_ids=event_stage_ids, rally_ids=rally_ids, ttl=ttl
        )
        await self.etl_event_stage_times(
            event_id=event_id, stage_ids=event_stage_ids, rally_ids=rally_ids, ttl=ttl
        )
        await self.etl_event_split_times(
            event_id=event_id, stage_ids=event_stage_ids, rally_ids=rally_ids, ttl=ttl
        )

    async def etl_event_rally_stage_results(
        self,
        event_id: int,
        stage_ids: list[int],
        rally_ids: list[int],
        ttl: timedelta | None = None,
    ) -> None:
        async with self._etl_run(EtlType.STAGE_RESULTS, event_id=event_id, ttl=ttl):
            futures = [
                get_event_stage_results_with_context(
                    client=self._api,
                    event_id=event_id,
                    rally_id=rally_id,
                    stage_id=stage_id,
                )
                for stage_id in stage_ids
                for rally_id in rally_ids
            ]
            stage_results = await asyncio.gather(*futures)
            async with self._db.session() as session:
                for stage_result, rally_id, stage_id in stage_results:
                    await upsert_stage_results(
                        session=session,
                        api_response=stage_result,
                        rally_id=rally_id,
                        stage_id=stage_id,
                    )
                await session.commit()

    async def etl_event_stage_times(
        self,
        event_id: int,
        stage_ids: list[int],
        rally_ids: list[int],
        ttl: timedelta | None = None,
    ) -> None:
        async with self._etl_run(EtlType.STAGE_TIMES, event_id=event_id, ttl=ttl):
            futures = [
                get_event_stage_times_with_context(
                    self._api, event_id=event_id, rally_id=rally_id, stage_id=stage_id
                )
                for rally_id in rally_ids
                for stage_id in stage_ids
            ]
            stage_time_results = await asyncio.gather(*futures)
            async with self._db.session() as session:
                for stage_time_result, rally_id, stage_id in stage_time_results:
                    await upsert_stage_time_results(
                        session=session,
                        api_response=stage_time_result,
                        rally_id=rally_id,
                    )
                await session.commit()

    async def etl_event_split_times(
        self,
        event_id: int,
        stage_ids: list[int],
        rally_ids: list[int],
        ttl: timedelta | None = None,
    ) -> None:
        async with self._etl_run(EtlType.SPLIT_TIMES, event_id=event_id, ttl=ttl):
            futures = [
                get_event_stage_split_times_with_context(
                    self._api, event_id=event_id, rally_id=rally_id, stage_id=stage_id
                )
                for rally_id in rally_ids
                for stage_id in stage_ids
            ]
            split_time_results = await asyncio.gather(*futures)
            async with self._db.session() as session:
                for split_time_result, rally_id, stage_id in split_time_results:
                    await upsert_split_time_results(
                        session=session,
                        api_response=split_time_result,
                        stage_id=stage_id,
                        rally_id=rally_id,
                    )
                await session.commit()

    async def _get_event_stages(self, event_id: int) -> list[Stage]:
        async with self._db.session() as session:
            result = await session.execute(
                select(Stage).where(Stage.event_id == event_id)
            )
            return list(result.scalars().all())

    async def _get_event_rallies(self, event_id: int) -> list[RallyMetadata]:
        async with self._db.session() as session:
            result = await session.execute(
                select(RallyMetadata).where(RallyMetadata.event_id == event_id)
            )
            return list(result.scalars().all())
