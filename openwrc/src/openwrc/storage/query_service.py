"""
Read-only query service for WRC data.
Exposes common query patterns against the local DB.
All methods take explicit IDs; see WrcSession for higher-level event-scoped access.
"""

from datetime import date

from sqlalchemy import distinct, extract, select

from openwrc.models.db.entities import Person
from openwrc.models.db.event import Entry, EventMetadata, RallyMetadata
from openwrc.models.db.itinerary import ItineraryLeg, ItinerarySection, Stage
from openwrc.models.db.result import RallyStanding, SplitTime
from openwrc.models.db.views import standings_select, split_times_select
from openwrc.services.read_models import FlatSplitTimeRow, FlatStandingRow
from openwrc.storage.database import WrcDatabase


class WrcQueryService:

    def __init__(self, db: WrcDatabase) -> None:
        self._db = db

    async def get_available_years(self) -> list[int]:
        """Return distinct years for which events exist, in ascending order."""
        stmt = select(distinct(extract("year", EventMetadata.start_date))).order_by(
            extract("year", EventMetadata.start_date)
        )
        async with self._db.session() as session:
            result = await session.execute(stmt)
            return [int(row) for row in result.scalars().all()]

    async def get_events_for_year(self, year: int) -> list[EventMetadata]:
        """Return all events for a given year, ordered by start date."""
        stmt = (
            select(EventMetadata)
            .where(extract("year", EventMetadata.start_date) == year)
            .order_by(EventMetadata.start_date)
        )
        async with self._db.session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_event_by_id(self, event_id: int) -> EventMetadata | None:
        """Return an event by its primary key."""
        stmt = select(EventMetadata).where(EventMetadata.event_id == event_id)
        async with self._db.session() as session:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_event_by_name(
        self, name: str, year: int | None = None
    ) -> EventMetadata | None:
        """Find an event by its name, optionally filtered by year.

        For most cases a bare name match is sufficient. Pass year when the same
        event name appears across multiple seasons (e.g. "Rallye Monte Carlo").
        """
        stmt = select(EventMetadata).where(EventMetadata.name.ilike(f"%{name}%"))
        if year is not None:
            stmt = stmt.where(
                EventMetadata.start_date >= f"{year}-01-01",
                EventMetadata.start_date < f"{year + 1}-01-01",
            )
        async with self._db.session() as session:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_default_rally_for_event(self, event_id: int) -> RallyMetadata | None:
        """Return the main rally for an event (is_main=True), falling back to the
        first rally by rally_id when no main rally is marked.
        """
        stmt = (
            select(RallyMetadata)
            .where(RallyMetadata.event_id == event_id)
            .order_by(RallyMetadata.is_main.desc(), RallyMetadata.rally_id)
        )
        async with self._db.session() as session:
            result = await session.execute(stmt)
            return result.scalars().first()

    async def get_stages_for_event(self, event_id: int) -> list[Stage]:
        """Return all stages for a given event, ordered by stage number."""
        stmt = select(Stage).where(Stage.event_id == event_id).order_by(Stage.number)
        async with self._db.session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_stages_for_event_by_date(
        self, event_id: int, leg_date: date
    ) -> list[Stage]:
        """Return all stages on a given leg date for an event, ordered by stage number.

        Joins Stage → ItinerarySection → ItineraryLeg to resolve the date.
        """
        stmt = (
            select(Stage)
            .join(
                ItinerarySection,
                Stage.itinerary_section_id == ItinerarySection.itinerary_section_id,
            )
            .join(
                ItineraryLeg,
                ItinerarySection.itinerary_leg_id == ItineraryLeg.itinerary_leg_id,
            )
            .where(Stage.event_id == event_id, ItineraryLeg.leg_date == leg_date)
            .order_by(Stage.number)
        )
        async with self._db.session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_stages_for_event_by_leg_order(
        self, event_id: int, leg_order: int
    ) -> list[Stage]:
        """Return all stages in a given leg (by its order index) for an event, ordered by stage number.

        Joins Stage → ItinerarySection → ItineraryLeg to resolve the leg order.
        """
        stmt = (
            select(Stage)
            .join(
                ItinerarySection,
                Stage.itinerary_section_id == ItinerarySection.itinerary_section_id,
            )
            .join(
                ItineraryLeg,
                ItinerarySection.itinerary_leg_id == ItineraryLeg.itinerary_leg_id,
            )
            .where(Stage.event_id == event_id, ItineraryLeg.order == leg_order)
            .order_by(Stage.number)
        )
        async with self._db.session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_stage_by_number(self, event_id: int, number: int) -> Stage | None:
        """Find a stage by its number within an event (e.g. number=5 → SS5)."""
        stmt = select(Stage).where(
            Stage.event_id == event_id,
            Stage.number == number,
        )
        async with self._db.session() as session:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_split_times(self, rally_id: int, stage_id: int) -> list[SplitTime]:
        """Return all split times for a given stage within a rally."""
        stmt = select(SplitTime).where(
            SplitTime.rally_id == rally_id,
            SplitTime.stage_id == stage_id,
        )
        async with self._db.session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_rally_entries(self, rally_id: int) -> list[Entry]:
        """Return all entries for a given rally."""
        stmt = select(Entry).where(Entry.rally_id == rally_id)
        async with self._db.session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_rally_drivers(self, rally_id: int) -> list[Person]:
        """Return Person rows for all drivers entered in a given rally."""
        stmt = (
            select(Person)
            .join(Entry, Entry.driver_id == Person.person_id)
            .where(Entry.rally_id == rally_id)
        )
        async with self._db.session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_rally_standings(
        self, rally_id: int, stage_id: int | None = None
    ) -> list[RallyStanding]:
        """Return rally standings for a given rally.

        When stage_id is provided, returns standings after that specific stage only.
        When omitted, returns all standings across all stages (full progression).
        """
        stmt = select(RallyStanding).where(RallyStanding.rally_id == rally_id)
        if stage_id is not None:
            stmt = stmt.where(RallyStanding.stage_id == stage_id)
        async with self._db.session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_flat_standings(
        self,
        rally_id: int,
        stage_id: int | None = None,
        entry_ids: set[int] | None = None,
    ) -> list[FlatStandingRow]:
        """Return denormalized standings rows with driver/manufacturer/class identity baked in.

        When stage_id is provided, returns the snapshot after that stage only.
        When omitted, returns all stages (full progression).
        entry_ids filters to a subset of entries; pass None to include all.
        """
        stmt = standings_select.where(RallyStanding.rally_id == rally_id).order_by(
            Stage.number, RallyStanding.position
        )
        if stage_id is not None:
            stmt = stmt.where(RallyStanding.stage_id == stage_id)
        if entry_ids is not None:
            stmt = stmt.where(RallyStanding.entry_id.in_(entry_ids))

        async with self._db.session() as session:
            result = await session.execute(stmt)
            return [
                FlatStandingRow.model_validate(dict(row))
                for row in result.mappings().all()
            ]

    async def get_flat_split_times(
        self,
        rally_id: int,
        stage_id: int,
        entry_ids: set[int] | None = None,
    ) -> list[FlatSplitTimeRow]:
        """Return denormalized split time rows with driver/manufacturer identity baked in.

        entry_ids filters to a subset of entries; pass None to include all.
        Rows are ordered by split_point_id then elapsed_duration_ms (ascending).
        """
        stmt = split_times_select.where(
            SplitTime.rally_id == rally_id, SplitTime.stage_id == stage_id
        ).order_by(SplitTime.split_point_id, SplitTime.elapsed_duration_ms)
        if entry_ids is not None:
            stmt = stmt.where(SplitTime.entry_id.in_(entry_ids))

        async with self._db.session() as session:
            result = await session.execute(stmt)
            return [
                FlatSplitTimeRow.model_validate(dict(row))
                for row in result.mappings().all()
            ]
