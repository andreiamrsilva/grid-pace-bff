"""Models for rally itinerary (schedule, stages, controls) from WRC API"""

from datetime import datetime, date
from pydantic import Field, ConfigDict
from .base_external_model import WrcExternalApiBaseModel


class ApiControl(WrcExternalApiBaseModel):
    """
    A control point in the rally (time control, stage start/finish, etc.)
    """

    model_config = ConfigDict(extra="ignore")

    control_id: int = Field(description="Unique identifier for this control")
    event_id: int
    stage_id: int | None = Field(None, description="Associated stage ID if applicable")

    # Control details
    type: str = Field(
        description="Control type (TimeControl, StageStart, FlyingFinish, etc.)"
    )
    code: str = Field(description="Control code (TC1, SS1, SF1, etc.)")
    location: str = Field(description="Control location name")
    status: str = Field(description="Control status (Scheduled, Completed, Cancelled)")

    # Timing details
    timing_precision: str = Field(description="Timing precision (Minute, Tenth, etc.)")
    distance: float | None = Field(None, description="Distance to this control in km")
    target_duration_ms: int | None = Field(
        None, description="Target duration in milliseconds"
    )

    first_car_due_date_time: datetime | None = Field(
        None, description="When first car is due (UTC)"
    )
    first_car_due_date_time_local: datetime | None = Field(
        None, description="When first car is due (local time with timezone)"
    )

    # Penalty and rounding rules
    control_penalties: str = Field(description="Penalty type (All, Late, None, etc.)")
    rounding_policy: str = Field(
        description="Rounding policy (NoRounding, RoundToClosestMinute, etc.)"
    )  # TODO: make into enum

    locked: bool = Field(description="Whether control is locked")
    bogey_ms: int | None = Field(None, description="Bogey time in milliseconds")


class ApiStage(WrcExternalApiBaseModel):
    """A special stage in the rally"""

    stage_id: int = Field(description="Unique identifier for this stage")
    event_id: int
    number: int = Field(description="Stage number (e.g., 1, 2, 3)")
    name: str = Field(description="Stage name")
    distance: float = Field(description="Stage distance in km")
    status: str = Field(description="Stage status (Scheduled, Completed, Cancelled)")
    stage_type: str = Field(
        description="Type of stage (e.g., HeadToHeadSuperSpecialStage, StandardStage)"
    )  # TODO: make into enum
    timing_precision: str = Field(
        description="Timing precision (Tenth, Hundredth)"
    )  # TODO: make into enum
    locked: bool = Field(description="Whether stage is locked")
    code: str = Field(description="Stage code (e.g., SS1, SS2)")


class ApiItinerarySection(WrcExternalApiBaseModel):
    """A section within a leg (group of stages and controls)"""

    model_config = ConfigDict(extra="ignore")

    itinerary_section_id: int = Field(description="Unique identifier for this section")
    itinerary_leg_id: int = Field(description="Parent leg ID")
    order: int = Field(description="Section order within leg")
    name: str = Field(description="Section name")

    controls: list[ApiControl] = Field(
        default_factory=list, description="All control points in this section"
    )
    stages: list[ApiStage] = Field(
        default_factory=list, description="All stages in this section"
    )


class ApiItineraryLeg(WrcExternalApiBaseModel):
    """A leg of the rally (typically one day)"""

    model_config = ConfigDict(extra="ignore")

    itinerary_leg_id: int = Field(description="Unique identifier for this leg")
    itinerary_id: int = Field(description="Parent itinerary ID")
    start_list_id: int | None = Field(None, description="Start list ID for this leg")

    name: str = Field(description="Leg name (e.g., 'Wednesday 26th November')")
    leg_date: date = Field(description="Date of this leg")
    order: int = Field(description="Leg order (1, 2, 3, etc.)")
    status: str = Field(description="Leg status (Scheduled, Completed, Cancelled)")

    itinerary_sections: list[ApiItinerarySection] = Field(
        default_factory=list, description="All sections in this leg"
    )


class ApiItinerary(WrcExternalApiBaseModel):
    """
    Complete itinerary for a rally.
    Contains the full schedule with all legs, sections, stages, and controls.
    """

    itinerary_legs: list[ApiItineraryLeg] = Field(
        default_factory=list, description="All legs (days) of the rally"
    )

    itinerary_id: int
    event_id: int
