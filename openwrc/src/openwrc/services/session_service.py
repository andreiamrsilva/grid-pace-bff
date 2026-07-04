from datetime import date
from enum import Enum
from zoneinfo import ZoneInfo

from openwrc.exceptions.session_exceptions import SessionInputValidationException
from openwrc.models.db.entities import Person
from openwrc.models.db.event import Entry, EventMetadata
from openwrc.models.db.itinerary import Stage
from openwrc.models.db.result import RallyStanding
from openwrc.services.data_service import WrcDataService
from openwrc.services.read_models import FlatSplitTimeRow, FlatStandingRow
from openwrc.storage.database import WrcDatabase
from openwrc.utils.datetime_utils import event_tz
from openwrc.utils.entity_to_id_mapping_utils import (
    map_car_identifier_to_entry_id,
    map_driver_name_to_entry_id,
    map_stage_code_to_stage_id,
)


class StandingsMetric(Enum):
    GAP_TO_FIRST = RallyStanding.diff_first_ms.key
    POSITION = RallyStanding.position.key
    TOTAL_TIME = RallyStanding.total_time_ms.key


class WrcSession:
    """
    Event-scoped entry point for querying WRC data from the local DB.

    Resolves event and rally identity once at creation time; all query methods
    use the resolved IDs so callers never have to pass them explicitly.

    Initialization options:
    - event_id: use the raw WRC event id directly
    - name + optional year: resolve event by name (e.g. name="monte carlo", year=2025)

    In both cases rally_id defaults to the main rally for the event.
    """

    def __init__(
        self,
        event_id: int,
        rally_id: int,
        data_svc: WrcDataService,
        event_start_date: date,
        event_finish_date: date,
        event_timezone: ZoneInfo,
    ):
        self.event_id = event_id
        self.rally_id = rally_id
        self.event_start_date = event_start_date
        self.event_finish_date = event_finish_date
        self.event_timezone = event_timezone
        self._data_svc = data_svc
        self._driver_name_map: dict[str, int] | None = None
        self._stage_code_map: dict[str, int] | None = None
        self._car_identifier_map: dict[str, int] | None = None

    @classmethod
    async def list_available_years(cls, db: WrcDatabase | None = None) -> list[int]:
        """Return distinct years for which events are stored in the local DB."""
        return await WrcDataService(db=db).get_available_years()

    @classmethod
    async def list_events_for_year(
        cls, year: int, db: WrcDatabase | None = None
    ) -> list[EventMetadata]:
        """Return all events stored for a given year, ordered by start date."""
        return await WrcDataService(db=db).get_events_for_year(year=year)

    @classmethod
    async def create(
        cls,
        *,
        event_id: int | None = None,
        name: str | None = None,
        year: int | None = None,
        rally_id: int | None = None,
        db: WrcDatabase | None = None,
    ) -> "WrcSession":
        if event_id is None and name is None:
            raise SessionInputValidationException(
                message="Provide either event_id or name to start a session."
            )

        data_svc = WrcDataService(db=db)
        event = await data_svc.resolve_event(event_id=event_id, name=name, year=year)

        if event is None:
            if event_id is not None:
                raise SessionInputValidationException(
                    message=f"No event found with event_id={event_id}."
                )
            detail = f"year={year}" if year else "no year filter"
            raise SessionInputValidationException(
                message=f"No event found matching name='{name}' ({detail})."
            )

        resolved_rally_id: int
        if rally_id is not None:
            resolved_rally_id = rally_id
        else:
            rally = await data_svc.get_default_rally_for_event(event_id=event.event_id)
            if rally is None:
                raise SessionInputValidationException(
                    message=f"No rally found for event_id={event.event_id}."
                )
            resolved_rally_id = rally.rally_id

        return cls(
            event_id=event.event_id,
            rally_id=resolved_rally_id,
            data_svc=data_svc,
            event_start_date=event.start_date.date(),
            event_finish_date=event.finish_date.date(),
            event_timezone=event_tz(event.time_zone_id),
        )

    async def entries(self) -> list[Entry]:
        """Return all entries for this rally."""
        return await self._data_svc.get_rally_entries(rally_id=self.rally_id)

    async def stages(self) -> list[Stage]:
        """Return all stages for this event, ordered by stage number."""
        return await self._data_svc.get_stages_for_event(event_id=self.event_id)

    async def get_rally_drivers(self) -> list[Person]:
        """Return Person rows for all drivers entered in this rally."""
        return await self._data_svc.get_rally_drivers(rally_id=self.rally_id)

    async def get_driver_name_to_entry_id(self) -> dict[str, int]:
        """Return a case-insensitive map from driver name variants to entry_id.

        Populated on first call and cached for the session lifetime.
        Accepts last name, full name, abbreviated name, or driver code as keys.
        """
        if self._driver_name_map is None:
            entries = await self.entries()
            drivers = await self.get_rally_drivers()
            self._driver_name_map = map_driver_name_to_entry_id(entries, drivers)
        return self._driver_name_map

    async def get_stage_code_to_stage_id(self) -> dict[str, int]:
        """Return a case-insensitive map from stage code to stage_id (e.g. 'ss3' → id).

        Populated on first call and cached for the session lifetime.
        """
        if self._stage_code_map is None:
            stages = await self.stages()
            self._stage_code_map = map_stage_code_to_stage_id(stages)
        return self._stage_code_map

    async def get_car_identifier_to_entry_id(self) -> dict[str, int]:
        """Return a map from car number string to entry_id (e.g. '1' → id).

        Populated on first call and cached for the session lifetime.
        """
        if self._car_identifier_map is None:
            entries = await self.entries()
            self._car_identifier_map = map_car_identifier_to_entry_id(entries)
        return self._car_identifier_map

    async def get_entry_id_to_driver_label(self) -> dict[int, str]:
        """Return a map from entry_id to driver abbreviated name (e.g. 'E. EVANS').

        Derived from the first stage's flat standings so no separate lookup is needed.
        """
        rows = await self.flat_standings()
        return {row.entry_id: row.driver_name for row in rows}

    async def get_standings_progression(
        self,
        metric: StandingsMetric,
        entry_ids: set[int] | None = None,
    ) -> tuple[list[int], dict[int, str], dict[int, dict[int, int | None]]]:
        """Fetch standings and build the progression matrix for the given metric.

        Returns:
            ordered_stage_ids: stage_ids in ascending order
            stage_id_to_code:  {stage_id: "SS1"} label map for column headers
            matrix:            {entry_id: {stage_id: metric_value}}

        entry_ids filters to a subset of entries; pass None to include all.
        """
        rows = await self.flat_standings(entry_ids=entry_ids)

        stage_id_to_code = {row.stage_id: row.stage_code for row in rows}
        matrix: dict[int, dict[int, int | None]] = {}
        for row in rows:
            matrix.setdefault(row.entry_id, {})[row.stage_id] = getattr(
                row, metric.value
            )

        ordered_stage_ids = sorted(stage_id_to_code)
        return ordered_stage_ids, stage_id_to_code, matrix

    async def flat_standings(
        self,
        stage_id: int | None = None,
        stage_number: int | None = None,
        entry_ids: set[int] | None = None,
    ) -> list[FlatStandingRow]:
        """Return denormalized standings rows with driver/manufacturer/class identity baked in.

        Ensures timing data is fresh before querying.
        Optionally filter to a specific stage (by id or number) and/or a subset of entries.
        """
        if stage_number is not None:
            stage = await self._data_svc.get_stage_by_number(
                event_id=self.event_id, number=stage_number
            )
            if stage is None:
                raise SessionInputValidationException(
                    message=f"No stage found with number={stage_number} in event_id={self.event_id}."
                )
            stage_id = stage.stage_id
        return await self._data_svc.get_flat_standings(
            event_id=self.event_id,
            rally_id=self.rally_id,
            stage_id=stage_id,
            entry_ids=entry_ids,
        )

    async def flat_split_times(
        self,
        stage_id: int | None = None,
        stage_number: int | None = None,
        entry_ids: set[int] | None = None,
    ) -> list[FlatSplitTimeRow]:
        """Return denormalized split time rows with driver/manufacturer identity baked in.

        Ensures timing data is fresh before querying.
        Requires either stage_id or stage_number.
        """
        if stage_id is None:
            if stage_number is None:
                raise SessionInputValidationException(
                    message="Provide either stage_id or stage_number."
                )
            stage = await self._data_svc.get_stage_by_number(
                event_id=self.event_id, number=stage_number
            )
            if stage is None:
                raise SessionInputValidationException(
                    message=f"No stage found with number={stage_number} in event_id={self.event_id}."
                )
            stage_id = stage.stage_id
        return await self._data_svc.get_flat_split_times(
            event_id=self.event_id,
            rally_id=self.rally_id,
            stage_id=stage_id,
            entry_ids=entry_ids,
        )
