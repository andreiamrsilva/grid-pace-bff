"""
WrcDataService — internal orchestrator between WrcSession and WrcEtlService.

Owns the three-tier refresh policy (catalog → event_info → timing) and
freshness checks via EtlRunLog. Consumers never call this directly; WrcSession
uses it internally before querying the DB.

Cooldown and in-flight deduplication are *not* implemented in v1 — single
local process with SQLite serializes writes naturally. Add them before
exposing a multi-caller / hosted path.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import and_, select

from openwrc.models.db.entities import Person
from openwrc.models.db.event import Entry, EventMetadata, RallyMetadata
from openwrc.models.db.itinerary import Stage
from openwrc.services.read_models import FlatSplitTimeRow, FlatStandingRow
from openwrc.models.db.logs import EtlRunLog, EtlType
from openwrc.storage.data_store_service import WrcEtlService
from openwrc.storage.database import WrcDatabase
from openwrc.storage.query_service import WrcQueryService


# ---------------------------------------------------------------------------
# Policy context
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class RefreshContext:
    """
    Carries optional event-level data so TTL policy functions can branch on
    event lifecycle state (live, finished, pre-event).

    'now' can be injected for deterministic tests; defaults to UTC time at
    construction.
    """

    event: EventMetadata | None = None
    now: datetime = dataclasses.field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def event_is_finished(self) -> bool:
        if self.event is None:
            return False
        finish = self.event.finish_date
        if finish.tzinfo is None:
            finish = finish.replace(tzinfo=timezone.utc)
        return self.now > finish

    @property
    def event_is_live(self) -> bool:
        if self.event is None:
            return False
        start = self.event.start_date
        finish = self.event.finish_date
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if finish.tzinfo is None:
            finish = finish.replace(tzinfo=timezone.utc)
        return start <= self.now <= finish


# ---------------------------------------------------------------------------
# Scope registry
# ---------------------------------------------------------------------------

TtlPolicy = Callable[[RefreshContext], timedelta | None]


@dataclasses.dataclass(frozen=True)
class RefreshScope:
    """
    Defines one entry in the refresh scope registry.

    level           – human-readable name (matches ETL tier in the plan).
    etl_types       – the EtlType values that this scope refreshes. Used to
                      query the latest completed EtlRunLog row: the scope is
                      considered stale when *any* of these types is stale or
                      missing.
    ttl_policy      – pure function: RefreshContext → timedelta | None.
                      None means data never expires (historical static).
    """

    level: str
    etl_types: tuple[EtlType, ...]
    ttl_policy: TtlPolicy


# ---------------------------------------------------------------------------
# TTL policy functions
# ---------------------------------------------------------------------------


def _catalog_ttl(ctx: RefreshContext) -> timedelta | None:
    # Refresh catalog roughly once a month — infrequent enough to not hammer the API
    # but frequent enough to pick up new events, date changes, or season rollover.
    return timedelta(days=30)


def _event_info_ttl(ctx: RefreshContext) -> timedelta | None:
    if ctx.event is None or ctx.event_is_finished:
        # Historical / finished events are immutable.
        return None
    if ctx.event_is_live:
        # Refresh structural data every 2 hours during live events.
        return timedelta(hours=2)
    # Pre-event: refresh once a day as entries/itinerary may update.
    return timedelta(hours=24)


def _timing_ttl(ctx: RefreshContext) -> timedelta | None:
    if ctx.event is None or ctx.event_is_finished:
        # Timing for finished events is static.
        return None
    if ctx.event_is_live:
        # Refresh timing data every 5 minutes during live events.
        return timedelta(minutes=5)
    # Pre-event: timings don't exist yet; refresh on demand only.
    return None


# ---------------------------------------------------------------------------
# Scope registry (ordered: catalog → event_info → timing)
# ---------------------------------------------------------------------------

CATALOG_SCOPE = RefreshScope(
    level="catalog",
    etl_types=(EtlType.CATALOG,),
    ttl_policy=_catalog_ttl,
)

EVENT_INFO_SCOPE = RefreshScope(
    level="event_info",
    etl_types=(EtlType.EVENT_METADATA, EtlType.ITINERARY, EtlType.ENTRIES),
    ttl_policy=_event_info_ttl,
)

TIMING_SCOPE = RefreshScope(
    level="timing",
    etl_types=(EtlType.STAGE_RESULTS, EtlType.STAGE_TIMES, EtlType.SPLIT_TIMES),
    ttl_policy=_timing_ttl,
)


# ---------------------------------------------------------------------------
# WrcDataService
# ---------------------------------------------------------------------------


class WrcDataService:
    """
    Internal orchestrator. Checks EtlRunLog freshness and triggers the
    corresponding WrcEtlService method when data is stale or missing.

    Also exposes the query methods that WrcSession needs so the session only
    has one internal dependency — no separate WrcQueryService reference required.

    Hierarchical ensures:
        ensure_catalog_fresh()
            └─ ensure_event_info_fresh(event_id)
                    └─ ensure_timing_fresh(event_id)
    """

    def __init__(
        self,
        db: WrcDatabase | None = None,
        etl: WrcEtlService | None = None,
    ) -> None:
        _db = db or WrcDatabase()
        self._db = _db
        self._etl = etl or WrcEtlService(db=_db)
        self._qs = WrcQueryService(db=_db)

    @property
    def query_service(self) -> WrcQueryService:
        """Exposes the underlying query service for use by WrcSession instance methods."""
        return self._qs

    # ------------------------------------------------------------------
    # EtlRunLog helpers
    # ------------------------------------------------------------------

    async def _latest_run(
        self, etl_type: EtlType, event_id: int | None
    ) -> EtlRunLog | None:
        """Return the most recent completed EtlRunLog row for (type, event_id)."""
        stmt = (
            select(EtlRunLog)
            .where(
                and_(
                    EtlRunLog.etl_type == etl_type.value,
                    EtlRunLog.event_id == event_id,
                    EtlRunLog.completed_at.is_not(None),
                )
            )
            .order_by(EtlRunLog.completed_at.desc())
            .limit(1)
        )
        async with self._db.session() as session:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    def _is_stale(self, run: EtlRunLog | None, now: datetime) -> bool:
        """Return True when run is missing or its expires_at is in the past."""
        if run is None:
            return True
        if run.expires_at is None:
            return False  # infinite TTL — never stale
        expires = run.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return now > expires

    async def _scope_needs_refresh(
        self,
        scope: RefreshScope,
        event_id: int | None,
        now: datetime,
    ) -> bool:
        """Return True if any EtlType in scope is stale or missing."""
        for etl_type in scope.etl_types:
            run = await self._latest_run(etl_type=etl_type, event_id=event_id)
            if self._is_stale(run, now):
                return True
        return False

    # ------------------------------------------------------------------
    # Hierarchical ensures
    # ------------------------------------------------------------------

    async def ensure_catalog_fresh(self, now: datetime | None = None) -> None:
        """
        Ensure seasons + catalog-level EventMetadata are present and fresh.
        No parent; always the first ensure in the chain.
        """
        _now = now or datetime.now(timezone.utc)
        ctx = RefreshContext(event=None, now=_now)

        if not await self._scope_needs_refresh(CATALOG_SCOPE, event_id=None, now=_now):
            return

        ttl = CATALOG_SCOPE.ttl_policy(ctx)
        await self._etl.etl_season_catalog(ttl=ttl)

    async def ensure_event_info_fresh(
        self, event_id: int, now: datetime | None = None
    ) -> None:
        """
        Ensure event metadata, itineraries, and entries for event_id are fresh.
        Calls ensure_catalog_fresh first so the event row is guaranteed to exist.
        """
        _now = now or datetime.now(timezone.utc)

        await self.ensure_catalog_fresh(now=_now)

        event = await self._qs.get_event_by_id(event_id=event_id)
        ctx = RefreshContext(event=event, now=_now)

        if not await self._scope_needs_refresh(
            EVENT_INFO_SCOPE, event_id=event_id, now=_now
        ):
            return

        ttl = EVENT_INFO_SCOPE.ttl_policy(ctx)
        await self._etl.etl_event_info(event_id=event_id, ttl=ttl)

    async def ensure_timing_fresh(
        self, event_id: int, now: datetime | None = None
    ) -> None:
        """
        Ensure stage results, stage times, and split times for event_id are fresh.
        Calls ensure_event_info_fresh first so stages and rallies exist in DB.
        """
        _now = now or datetime.now(timezone.utc)

        await self.ensure_event_info_fresh(event_id=event_id, now=_now)

        event = await self._qs.get_event_by_id(event_id=event_id)
        ctx = RefreshContext(event=event, now=_now)

        if not await self._scope_needs_refresh(
            TIMING_SCOPE, event_id=event_id, now=_now
        ):
            return

        ttl = TIMING_SCOPE.ttl_policy(ctx)
        await self._etl.etl_event_timings(event_id=event_id, ttl=ttl)

    # ------------------------------------------------------------------
    # Combined ensure + query methods (used by WrcSession classmethods)
    # ------------------------------------------------------------------

    async def get_available_years(self) -> list[int]:
        """Ensure catalog is fresh, then return distinct event years."""
        await self.ensure_catalog_fresh()
        return await self._qs.get_available_years()

    async def get_events_for_year(self, year: int) -> list[EventMetadata]:
        """Ensure catalog is fresh, then return events for the given year."""
        await self.ensure_catalog_fresh()
        return await self._qs.get_events_for_year(year=year)

    async def resolve_event(
        self,
        event_id: int | None = None,
        name: str | None = None,
        year: int | None = None,
    ) -> EventMetadata | None:
        """
        Resolve event identity with freshness guarantees.

        - By event_id: checks DB first; falls back to catalog refresh if missing.
          Then ensures event-info is fresh and re-fetches the row.
        - By name: ensures catalog is fresh first so the event is discoverable,
          then resolves by name. Ensures event-info is fresh before returning.

        Returns None if the event cannot be found after all refresh attempts.
        """
        if event_id is None and name is None:
            return None

        if event_id is None:
            await self.ensure_catalog_fresh()
            event = await self._qs.get_event_by_name(name=name, year=year)
            if event is None:
                return None
            event_id = event.event_id
        else:
            event = await self._qs.get_event_by_id(event_id=event_id)
            if event is None:
                # Not yet in DB — try a catalog pull to discover it.
                await self.ensure_catalog_fresh()
                event = await self._qs.get_event_by_id(event_id=event_id)
            if event is None:
                return None
            event_id = event.event_id

        await self.ensure_event_info_fresh(event_id=event_id)
        # Re-fetch to return the post-ETL version of the row.
        return await self._qs.get_event_by_id(event_id=event_id)

    async def get_default_rally_for_event(self, event_id: int) -> RallyMetadata | None:
        return await self._qs.get_default_rally_for_event(event_id=event_id)

    async def get_rally_entries(self, rally_id: int) -> list[Entry]:
        return await self._qs.get_rally_entries(rally_id=rally_id)

    async def get_stages_for_event(self, event_id: int) -> list[Stage]:
        return await self._qs.get_stages_for_event(event_id=event_id)

    async def get_rally_drivers(self, rally_id: int) -> list[Person]:
        return await self._qs.get_rally_drivers(rally_id=rally_id)

    async def get_stage_by_number(self, event_id: int, number: int) -> Stage | None:
        return await self._qs.get_stage_by_number(event_id=event_id, number=number)

    async def get_flat_standings(
        self,
        event_id: int,
        rally_id: int,
        stage_id: int | None = None,
        entry_ids: set[int] | None = None,
    ) -> list[FlatStandingRow]:
        """Ensure timing data is fresh, then return denormalized standings rows."""
        await self.ensure_timing_fresh(event_id=event_id)
        return await self._qs.get_flat_standings(
            rally_id=rally_id, stage_id=stage_id, entry_ids=entry_ids
        )

    async def get_flat_split_times(
        self,
        event_id: int,
        rally_id: int,
        stage_id: int,
        entry_ids: set[int] | None = None,
    ) -> list[FlatSplitTimeRow]:
        """Ensure timing data is fresh, then return denormalized split time rows."""
        await self.ensure_timing_fresh(event_id=event_id)
        return await self._qs.get_flat_split_times(
            rally_id=rally_id, stage_id=stage_id, entry_ids=entry_ids
        )
