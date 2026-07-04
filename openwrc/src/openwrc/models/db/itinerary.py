from datetime import datetime, date
from sqlalchemy import String, ForeignKey, Enum
from enum import Enum as PyEnum
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .event import EventMetadata, RallyMetadata


class Itinerary(Base):
    __tablename__ = "itineraries"

    # Primary key
    itinerary_id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign keys
    event_id: Mapped[int] = mapped_column(ForeignKey(EventMetadata.event_id))
    rally_id: Mapped[int] = mapped_column(ForeignKey(RallyMetadata.rally_id))


class ItineraryLeg(Base):
    __tablename__ = "itinerary_legs"

    # Primary key
    itinerary_leg_id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign keys
    itinerary_id: Mapped[int] = mapped_column(ForeignKey(Itinerary.itinerary_id))
    start_list_id: Mapped[int | None] = mapped_column(
        ForeignKey("start_lists.start_list_id")
    )

    # Leg info
    name: Mapped[str] = mapped_column(String(200))  # "Wednesday 26th November"
    leg_date: Mapped[date]
    order: Mapped[int]  # 1, 2, 3, etc.
    status: Mapped[str] = mapped_column(
        String(50)
    )  # "Scheduled", "Completed", "Cancelled"


class ItinerarySection(Base):
    __tablename__ = "itinerary_sections"

    # Primary key
    itinerary_section_id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign keys
    itinerary_leg_id: Mapped[int] = mapped_column(
        ForeignKey(ItineraryLeg.itinerary_leg_id)
    )

    # Section info
    name: Mapped[str] = mapped_column(String(200))
    order: Mapped[int]


class Stage(Base):
    __tablename__ = "stages"

    # Primary key
    stage_id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign keys
    event_id: Mapped[int] = mapped_column(ForeignKey(EventMetadata.event_id))
    itinerary_section_id: Mapped[int] = mapped_column(
        ForeignKey(ItinerarySection.itinerary_section_id)
    )

    # Stage info
    number: Mapped[int]  # Stage number (1, 2, 3, ...)
    name: Mapped[str] = mapped_column(String(200))
    distance: Mapped[float]  # km
    status: Mapped[str] = mapped_column(
        String(50)
    )  # "Scheduled", "Completed", "Cancelled"
    stage_type: Mapped[str] = mapped_column(
        String(100)
    )  # "StandardStage", "HeadToHeadSuperSpecialStage"
    timing_precision: Mapped[str] = mapped_column(String(50))  # "Tenth", "Hundredth"
    locked: Mapped[bool]
    code: Mapped[str] = mapped_column(String(20))  # "SS1", "SS2"


class Control(Base):
    __tablename__ = "controls"

    # Primary key
    control_id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign keys
    event_id: Mapped[int] = mapped_column(ForeignKey(EventMetadata.event_id))
    itinerary_section_id: Mapped[int] = mapped_column(
        ForeignKey(ItinerarySection.itinerary_section_id)
    )
    stage_id: Mapped[int | None] = mapped_column(ForeignKey(Stage.stage_id))  # Optional

    # Control details
    type: Mapped[str] = mapped_column(
        String(50)
    )  # "TimeControl", "StageStart", "FlyingFinish"
    code: Mapped[str] = mapped_column(String(20))  # "TC1", "SS1", "SF1"
    location: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(50)
    )  # "Scheduled", "Completed", "Cancelled"

    # Timing details
    timing_precision: Mapped[str] = mapped_column(String(50))  # "Minute", "Tenth"
    distance: Mapped[float | None]  # km
    target_duration_ms: Mapped[int | None]

    # Datetime fields (UTC)
    first_car_due_date_time: Mapped[datetime | None]
    first_car_due_date_time_local: Mapped[datetime | None]

    # Penalty and rounding rules
    control_penalties: Mapped[str] = mapped_column(String(50))  # "All", "Late", "None"
    rounding_policy: Mapped[str] = mapped_column(
        String(50)
    )  # "NoRounding", "RoundToClosestMinute"
    locked: Mapped[bool]
    bogey_ms: Mapped[int | None]


class StartListPublishStatus(PyEnum):
    PUBLISHED = "Published"
    UNPUBLISHED = "Unpublished"


class StartList(Base):
    __tablename__ = "start_lists"

    # Primary key
    start_list_id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign keys
    event_id: Mapped[int] = mapped_column(ForeignKey(EventMetadata.event_id))

    # Start list info
    name: Mapped[str] = mapped_column(String(200))  # "Thursday"
    published_status: Mapped[StartListPublishStatus] = mapped_column(
        Enum(StartListPublishStatus, native_enum=False)
    )


class StartListItem(Base):
    __tablename__ = "start_list_items"

    # Primary key
    start_list_item_id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign keys
    start_list_id: Mapped[int] = mapped_column(ForeignKey(StartList.start_list_id))
    entry_id: Mapped[int] = mapped_column(ForeignKey("entries.entry_id"))

    # Start details
    start_date_time: Mapped[datetime]  # UTC
    order: Mapped[int]  # Start order position
