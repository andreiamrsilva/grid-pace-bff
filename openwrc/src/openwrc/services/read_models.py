"""
Typed read models for denormalized query results.

These are Pydantic models returned by WrcQueryService methods that join across
multiple tables. They are the typed boundary between raw DB rows and calling
code (UI, agent, etc.).
"""

from pydantic import BaseModel


class ReadModel(BaseModel):
    model_config = {"frozen": True}


class FlatStandingRow(ReadModel):
    """Overall rally standings snapshot, one row per (entry, stage).

    Combines RallyStanding metrics with denormalized stage and entry identity
    so callers don't need to do any further lookups.
    """

    # span
    stage_id: int
    stage_number: int
    stage_code: str
    # entity dimensions
    entry_id: int
    driver_name: str  # Person.abbv_name  e.g. "E. EVANS"
    manufacturer_name: str  # Manufacturer.name e.g. "Toyota"
    entrant_name: str  # Entrant.name      e.g. "TOYOTA GAZOO RACING WRT"
    car_number: str  # Entry.identifier  e.g. "33"
    class_name: str | None  # EventClass.name   e.g. "RC1" — None if unclassified
    # metrics (all cumulative from rally start)
    position: int | None
    diff_first_ms: int | None
    total_time_ms: int | None  # stage_time_ms + penalty_time_ms
    stage_time_ms: int  # cumulative pure stage driving time, no penalties


class FlatSplitTimeRow(ReadModel):
    """Split point timing record, one row per (entry, split_point) within a stage.

    Combines SplitTime with denormalized stage and entry identity.
    elapsed_duration_ms is CUMULATIVE from stage start to this split point —
    not a per-segment duration.

    Note: the full set of split points for a stage can only be inferred from
    entries with a Completed stage status — retired entries have partial rows.
    """

    # span
    stage_id: int
    stage_number: int
    stage_code: str
    # split dimension (opaque — no distance/name metadata available from API)
    split_point_id: int
    # entity dimensions
    entry_id: int
    driver_name: str  # Person.abbv_name
    manufacturer_name: str  # Manufacturer.name
    car_number: str  # Entry.identifier
    class_name: str | None  # EventClass.name e.g. "RC1" — None if unclassified
    # metric
    elapsed_duration_ms: int  # cumulative from stage start to this split point
