from datetime import datetime
from typing import TypedDict
from sqlalchemy import String, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .entities import Country, Group, Manufacturer, Entrant, Person


class EventMetadataDetails(TypedDict):
    """
    Subset of EventMetadata columns written by the full /events/{id}.json endpoint.
    season_id and round_order are intentionally excluded — they are catalog-only
    fields populated by etl_season_catalog and must never be overwritten.
    """

    name: str
    location: str
    slug: str
    surfaces: str
    start_date: datetime
    finish_date: datetime
    time_zone_id: str
    time_zone_name: str
    country_id: int
    shakedown_count: int


class Season(Base):
    __tablename__ = "seasons"

    season_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    year: Mapped[int]


class EventMetadata(Base):
    __tablename__ = "events"

    # Primary key
    event_id: Mapped[int] = mapped_column(primary_key=True)

    # Season context
    season_id: Mapped[int] = mapped_column(ForeignKey(Season.season_id))
    round_order: Mapped[int]

    # Basic event info
    name: Mapped[str] = mapped_column(String(200))
    location: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100))
    surfaces: Mapped[str] = mapped_column(String(100))

    # Dates (stored as UTC)
    start_date: Mapped[datetime]
    finish_date: Mapped[datetime]

    # Timezone info
    time_zone_id: Mapped[str] = mapped_column(String(100))
    time_zone_name: Mapped[str] = mapped_column(String(100))

    # Foreign keys
    country_id: Mapped[int] = mapped_column(ForeignKey(Country.country_id))

    # Other metadata
    shakedown_count: Mapped[int] = mapped_column(default=0)


class RallyMetadata(Base):
    __tablename__ = "rallies"

    # Primary key
    rally_id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign keys
    event_id: Mapped[int] = mapped_column(ForeignKey(EventMetadata.event_id))
    itinerary_id: Mapped[int]

    # Rally info
    name: Mapped[str] = mapped_column(String(200))
    is_main: Mapped[bool] = mapped_column(default=False)


class EventClass(Base):
    __tablename__ = "event_classes"

    # Primary key
    event_class_id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign key
    event_id: Mapped[int] = mapped_column(ForeignKey(EventMetadata.event_id))

    # Class info
    name: Mapped[str] = mapped_column(String(50))


class Entry(Base):
    __tablename__ = "entries"

    # Primary key
    entry_id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign keys
    rally_id: Mapped[int] = mapped_column(ForeignKey(RallyMetadata.rally_id))

    driver_id: Mapped[int] = mapped_column(ForeignKey(Person.person_id))
    codriver_id: Mapped[int] = mapped_column(ForeignKey(Person.person_id))
    manufacturer_id: Mapped[int] = mapped_column(
        ForeignKey(Manufacturer.manufacturer_id)
    )
    entrant_id: Mapped[int] = mapped_column(ForeignKey(Entrant.entrant_id))
    group_id: Mapped[int] = mapped_column(ForeignKey(Group.group_id))

    # Entry details
    identifier: Mapped[str] = mapped_column(String(10))  # Car number
    vehicle_model: Mapped[str] = mapped_column(
        String(100)
    )  # "GR Yaris Rally1" # TODO: maybe its own table
    entry_list_order: Mapped[int]

    # Competition details
    eligibility: Mapped[str] = mapped_column(String(10))  # "M" for Manufacturer
    priority: Mapped[str] = mapped_column(String(10))  # "P1"
    status: Mapped[str] = mapped_column(String(50))  # "Entry", "Retired"
    tyre_manufacturer: Mapped[str] = mapped_column(
        String(50)
    )  # TODO: maybe its own table

    # Optional fields
    pbf: Mapped[str | None] = mapped_column(String(50))
    drive: Mapped[str | None] = mapped_column(String(50))
    tags: Mapped[list | None] = mapped_column(JSON)


class EntryEventClass(Base):
    __tablename__ = "entry_event_classes"
    # composite primary key
    event_class_id: Mapped[int] = mapped_column(
        ForeignKey(EventClass.event_class_id), primary_key=True
    )
    entry_id: Mapped[int] = mapped_column(ForeignKey(Entry.entry_id), primary_key=True)


class RallyEventClass(Base):
    __tablename__ = "rally_event_classes"

    # composite primary key
    rally_id: Mapped[int] = mapped_column(
        ForeignKey(RallyMetadata.rally_id), primary_key=True
    )
    event_class_id: Mapped[int] = mapped_column(
        ForeignKey(EventClass.event_class_id), primary_key=True
    )
