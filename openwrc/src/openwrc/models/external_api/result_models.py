from __future__ import annotations

"""
Models for rally and stage results from WRC API
Important Note: this is for the entire rally up to the stage. single stage models will be under stage_models.py
"""

from datetime import datetime
from typing import Optional
from pydantic import Field
from .base_external_model import WrcExternalApiBaseModel


class ApiBaseEntry(WrcExternalApiBaseModel):
    entry_id: int = Field(description="Entry ID for this driver/car combination")
    # Position and time differences
    position: Optional[int] = Field(
        default=None, description="Current position in standings"
    )
    diff_first_ms: Optional[int] = Field(
        default=None, description="Overall time difference to leader in milliseconds"
    )
    diff_prev_ms: Optional[int] = Field(
        default=None,
        description="Overall time difference to previous position in milliseconds",
    )


class ApiResultEntry(ApiBaseEntry):
    """A single result entry for a driver in a rally or stage"""

    # Time data in milliseconds (easier to work with)
    stage_time_ms: int = Field(description="Stage time in milliseconds")
    penalty_time_ms: int = Field(description="Penalty time in milliseconds")
    total_time_ms: int = Field(
        description="Total time (stage + penalty) in milliseconds"
    )


class ApiStageTimeEntry(ApiBaseEntry):
    """A single stage time entry for a driver's performance on a specific stage.

    Source: /{event_id}/stages/{stage_id}/stagetimes.json
    One record per entry. elapsed_duration_ms is the raw stage time (flying
    finish - stage start). Identical to the value derivable from controlTimes
    (FlyingFinish.actualDateTime - StageStart.actualDateTime) and also equal to
    split_times.stage_time_duration_ms for the same entry.
    """

    stage_id: int = Field(description="Stage ID")
    # Time from stage start to flying finish, in ms.
    elapsed_duration_ms: Optional[int] = Field(default=None)
    # TODO: make enum — known values: Completed, Retired, DidNotStart, Disqualified
    status: str = Field(description="Stage completion status")
    # TODO: make enum — known values: Default, Manual, Corrected
    source: str = Field(description="Timing data source")


class ApiShakedownTimeEntry(WrcExternalApiBaseModel):
    """A single shakedown time entry for a driver's shakedown run"""

    shakedown_time_id: int = Field(
        description="Unique identifier for this shakedown time"
    )
    event_id: int = Field(description="Event ID")
    entry_id: int = Field(description="Entry ID for this driver/car combination")
    run_number: int = Field(description="Run number (e.g., 1st run, 2nd run)")
    shakedown_number: int = Field(description="Shakedown stage number")
    run_duration_ms: int = Field(description="Run duration in milliseconds")


class ApiSplitTimeEntry(WrcExternalApiBaseModel):
    """A single split time entry for an entry at an intermediate split point.

    Source: /{event_id}/stages/{stage_id}/splittimes.json
    One record per (entry, split_point). Does NOT include the stage finish —
    the finish time is in ApiStageTimeEntry (stagetimes.json).
    """

    # Wall clock UTC time when this entry started the stage
    start_date_time: datetime = Field(description="Stage start time in UTC")
    # Wall clock UTC time when this entry passed this split point
    split_date_time: datetime = Field(description="Split point passage time in UTC")
    split_point_time_id: int = Field(description="Unique ID for this split time record")
    # Opaque ID for the split point. No ordering or distance metadata available
    # from the API — sort by elapsed_duration_ms to approximate physical order.
    split_point_id: int = Field(description="Split point ID (no distance metadata)")
    entry_id: int = Field(description="Entry ID")
    # CUMULATIVE time from stage start to this split point, in ms.
    # NOT the time since the previous split point.
    elapsed_duration_ms: int = Field(
        description="Cumulative time from stage start to this split point, in ms"
    )
    # The entry's total stage finish time, in ms. SAME value on every split row
    # for this entry — it is NOT the segment duration. Equivalent to
    # ApiStageTimeEntry.elapsed_duration_ms for the same (entry, stage).
    stage_time_duration_ms: int | None = Field(
        default=None,
        description="Entry's total stage finish time in ms (repeated on every split row)",
    )


# Type aliases for clarity
ApiRallyResults = list[ApiResultEntry]
ApiStageResults = list[ApiResultEntry]
ApiStageTimeResults = list[ApiStageTimeEntry]
ApiShakedownTimeResults = list[ApiShakedownTimeEntry]
ApiSplitTimeResults = list[ApiSplitTimeEntry]
