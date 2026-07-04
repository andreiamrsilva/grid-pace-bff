from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, ForeignKey, Enum, Index
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .event import EventMetadata, RallyMetadata, Entry
from .itinerary import Stage


class StageStatus(PyEnum):
    """Status of stage completion"""

    COMPLETED = "Completed"
    RETIRED = "Retired"
    DNF = "DNF"
    RUNNING = "Running"
    DID_NOT_START = "DNS"
    DISQUALIFIED = "Disqualified"
    EXCLUDED = "Excluded"


class DataSource(PyEnum):
    """Source of timing data"""

    DEFAULT = "Default"
    MANUAL = "Manual"
    CORRECTED = "Corrected"
    ASSESSED = "Assessed"


class StageTime(Base):
    """Individual driver performance on a specific stage.

    One row per (entry, stage). Records the raw stage time — how long the entry
    took to complete that single stage, independent of cumulative rally totals.

    Source: /{event_id}/stages/{stage_id}/stagetimes.json
    This is the same value as FlyingFinish controlTime - StageStart controlTime for the same entry.
    """

    __tablename__ = "stage_times"

    # Composite PK: one record per (stage, entry)
    stage_id: Mapped[int] = mapped_column(ForeignKey(Stage.stage_id), primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey(Entry.entry_id), primary_key=True)

    # Denormalized for query efficiency
    rally_id: Mapped[int] = mapped_column(ForeignKey(RallyMetadata.rally_id))

    # Time from stage start to flying finish for this entry, in ms.
    # None if the entry did not complete the stage (see status).
    elapsed_duration_ms: Mapped[int | None]
    # Stage position (rank among entries on this stage only, not overall)
    position: Mapped[int | None]
    # Gap to the stage winner, in ms. None if this entry is the stage winner.
    diff_first_ms: Mapped[int | None]
    # Gap to the entry ranked one position ahead on this stage, in ms.
    diff_prev_ms: Mapped[int | None]

    status: Mapped[StageStatus] = mapped_column(
        Enum(StageStatus, values_callable=lambda e: [m.value for m in e])
    )
    source: Mapped[str] = mapped_column(String(50))

    # Indexes for common queries
    __table_args__ = (
        Index("ix_stage_time_rally_entry", "rally_id", "entry_id"),
        Index("ix_stage_time_stage", "stage_id"),
    )


class RallyStanding(Base):
    """Overall rally standings for an entry after each completed stage.

    One row per (rally, stage, entry) — a snapshot of the overall standings
    at each point in the rally. All time fields are CUMULATIVE from the start
    of the rally, not per-stage.

    Source: /{event_id}/stages/{stage_id}/results.json
    """

    __tablename__ = "rally_standings"

    rally_id: Mapped[int] = mapped_column(
        ForeignKey(RallyMetadata.rally_id), primary_key=True
    )
    stage_id: Mapped[int] = mapped_column(ForeignKey(Stage.stage_id), primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey(Entry.entry_id), primary_key=True)

    # Overall position in the rally after this stage
    position: Mapped[int | None]
    # Cumulative competitive stage time (sum of all stage elapsed times so far), in ms.
    # Does NOT include penalties. To get individual stage time, diff consecutive
    # stage_time_ms values for the same entry ordered by stage number.
    stage_time_ms: Mapped[int]
    # Cumulative penalty time applied to this entry so far, in ms
    penalty_time_ms: Mapped[int]
    # stage_time_ms + penalty_time_ms — the official total used for classification
    total_time_ms: Mapped[int]
    # Gap to the overall rally leader at this point, in ms. None if this entry leads.
    diff_first_ms: Mapped[int | None]
    # Gap to the entry ranked one position ahead overall, in ms.
    diff_prev_ms: Mapped[int | None]

    # Indexes for common queries
    __table_args__ = (
        Index("ix_rally_standing_rally_entry", "rally_id", "entry_id"),
        Index("ix_rally_standing_rally_stage", "rally_id", "stage_id"),
    )


class ShakedownTime(Base):
    """Pre-rally shakedown run times"""

    __tablename__ = "shakedown_times"

    # Primary key
    shakedown_time_id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign keys
    event_id: Mapped[int] = mapped_column(ForeignKey(EventMetadata.event_id))
    entry_id: Mapped[int] = mapped_column(ForeignKey(Entry.entry_id))

    # Shakedown details
    run_number: Mapped[int]
    shakedown_number: Mapped[int]
    run_duration_ms: Mapped[int]

    # Indexes for common queries
    __table_args__ = (Index("ix_shakedown_event_entry", "event_id", "entry_id"),)


class SplitTime(Base):
    """Timing gate records within a stage for each entry.

    One row per (entry, split point). Split points are intermediate timing
    gates placed along the stage route — they do NOT include the stage finish.
    To get the stage finish time use stage_times.elapsed_duration_ms.

    Source: /{event_id}/stages/{stage_id}/splittimes.json
    """

    __tablename__ = "split_times"

    # Primary key
    split_point_time_id: Mapped[int] = mapped_column(primary_key=True)

    # Opaque ID for the split point. No SplitPoint table exists yet so there is
    # no distance or ordering metadata. Sort by min(elapsed_duration_ms) across
    # entries to approximate physical order along the stage.
    split_point_id: Mapped[int]
    rally_id: Mapped[int] = mapped_column(ForeignKey(RallyMetadata.rally_id))
    stage_id: Mapped[int] = mapped_column(ForeignKey(Stage.stage_id))
    entry_id: Mapped[int] = mapped_column(ForeignKey(Entry.entry_id))

    # Wall clock UTC time when this entry started the stage
    start_date_time: Mapped[datetime]
    # Wall clock UTC time when this entry passed this split point
    split_date_time: Mapped[datetime]
    # CUMULATIVE time from stage start to this split point, in ms.
    # NOT a per-segment duration. To get segment time, diff consecutive
    # elapsed_duration_ms values for the same entry ordered by elapsed value.
    elapsed_duration_ms: Mapped[int]

    # Indexes for common queries
    __table_args__ = (Index("ix_split_time_stage_entry", "stage_id", "entry_id"),)
