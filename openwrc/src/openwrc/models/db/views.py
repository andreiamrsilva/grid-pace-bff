"""
SQLite view definitions for denormalized read queries.

Each view is defined as a SQLAlchemy select() expression — the canonical
shape used for both:
  1. DDL: create_views(conn) emits CREATE VIEW IF NOT EXISTS statements
  2. Python queries: query_service methods add WHERE/ORDER BY on top

Call create_views(sync_conn) after Base.metadata.create_all to materialize
the views. WrcDatabase._ensure_schema does this automatically.
"""

from sqlalchemy import Select, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import aliased
from sqlalchemy.dialects import sqlite as sqlite_dialect

from .entities import Entrant, Manufacturer, Person
from .event import Entry, EntryEventClass, EventClass
from .itinerary import Stage
from .result import RallyStanding, SplitTime


# ---------------------------------------------------------------------------
# v_standings
# One row per (rally, stage, entry). Combines RallyStanding metrics with
# denormalized stage identity and entry identity (driver, manufacturer, etc.)
# ---------------------------------------------------------------------------

_standings_driver = aliased(Person)

_class_subq = (
    select(EventClass.name)
    .join(EntryEventClass, EventClass.event_class_id == EntryEventClass.event_class_id)
    .where(EntryEventClass.entry_id == Entry.entry_id)
    .order_by(EventClass.event_class_id)
    .limit(1)
    .correlate(Entry)
    .scalar_subquery()
)

standings_select = (
    select(
        RallyStanding.rally_id,
        RallyStanding.stage_id,
        Stage.number.label("stage_number"),
        Stage.code.label("stage_code"),
        RallyStanding.entry_id,
        _standings_driver.abbv_name.label("driver_name"),
        Manufacturer.name.label("manufacturer_name"),
        Entrant.name.label("entrant_name"),
        Entry.identifier.label("car_number"),
        _class_subq.label("class_name"),
        RallyStanding.position,
        RallyStanding.diff_first_ms,
        RallyStanding.total_time_ms,
        RallyStanding.stage_time_ms,
    )
    .join(Stage, RallyStanding.stage_id == Stage.stage_id)
    .join(Entry, RallyStanding.entry_id == Entry.entry_id)
    .join(_standings_driver, Entry.driver_id == _standings_driver.person_id)
    .join(Manufacturer, Entry.manufacturer_id == Manufacturer.manufacturer_id)
    .join(Entrant, Entry.entrant_id == Entrant.entrant_id)
)


# ---------------------------------------------------------------------------
# v_split_times
# One row per (rally, stage, split_point, entry). Combines SplitTime with
# denormalized stage and entry identity.
# ---------------------------------------------------------------------------

_split_driver = aliased(Person)

split_times_select = (
    select(
        SplitTime.rally_id,
        SplitTime.stage_id,
        Stage.number.label("stage_number"),
        Stage.code.label("stage_code"),
        SplitTime.split_point_id,
        SplitTime.entry_id,
        _split_driver.abbv_name.label("driver_name"),
        Manufacturer.name.label("manufacturer_name"),
        Entry.identifier.label("car_number"),
        _class_subq.label("class_name"),
        SplitTime.elapsed_duration_ms,
    )
    .join(Stage, SplitTime.stage_id == Stage.stage_id)
    .join(Entry, SplitTime.entry_id == Entry.entry_id)
    .join(_split_driver, Entry.driver_id == _split_driver.person_id)
    .join(Manufacturer, Entry.manufacturer_id == Manufacturer.manufacturer_id)
)


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------


def _to_sql(stmt: Select) -> str:
    return str(
        stmt.compile(
            dialect=sqlite_dialect.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def create_views(conn: Connection) -> None:
    """Create all views. Accepts a synchronous SQLAlchemy connection.

    Designed to be called via conn.run_sync(create_views) inside an async
    engine context, after Base.metadata.create_all has run.
    """
    conn.execute(
        text(f"CREATE VIEW IF NOT EXISTS v_standings AS {_to_sql(standings_select)}")
    )
    conn.execute(
        text(
            f"CREATE VIEW IF NOT EXISTS v_split_times AS {_to_sql(split_times_select)}"
        )
    )
