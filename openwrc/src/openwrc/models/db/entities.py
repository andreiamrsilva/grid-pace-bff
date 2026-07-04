from enum import Enum as PyEnum
from sqlalchemy import String, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PersonType(PyEnum):
    """Type of person in the database"""

    PERSON = "person"
    DRIVER = "driver"
    CODRIVER = "codriver"


class Country(Base):
    __tablename__ = "countries"

    # Primary key
    country_id: Mapped[int] = mapped_column(primary_key=True)

    # Country info
    name: Mapped[str] = mapped_column(String(200))
    iso2: Mapped[str] = mapped_column(String(2))
    iso3: Mapped[str] = mapped_column(String(3))


class Group(Base):
    __tablename__ = "groups"

    # Primary key
    group_id: Mapped[int] = mapped_column(primary_key=True)

    # Group info
    name: Mapped[str] = mapped_column(String(50))  # "Rally1", "Rally2", "Rally3"


class Manufacturer(Base):
    __tablename__ = "manufacturers"

    # Primary key
    manufacturer_id: Mapped[int] = mapped_column(primary_key=True)

    # Manufacturer info
    name: Mapped[str] = mapped_column(String(200))  # "Toyota", "Hyundai"
    logo_filename: Mapped[str | None] = mapped_column(String(200))


class Entrant(Base):
    __tablename__ = "entrants"

    # Primary key
    entrant_id: Mapped[int] = mapped_column(primary_key=True)

    # Team info
    name: Mapped[str] = mapped_column(String(200))  # "TOYOTA GAZOO RACING WRT"
    logo_filename: Mapped[str | None] = mapped_column(String(200))


class Person(Base):
    __tablename__ = "persons"

    # Primary key
    person_id: Mapped[int] = mapped_column(primary_key=True)

    # Discriminator for inheritance (stored as string in DB, but enum in Python)
    person_type: Mapped[PersonType] = mapped_column(Enum(PersonType))

    # Foreign keys
    country_id: Mapped[int] = mapped_column(ForeignKey(Country.country_id))

    # Optional IDs
    season_id: Mapped[int | None]
    external_id: Mapped[str | None] = mapped_column(String(100))

    # Name fields
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    abbv_name: Mapped[str] = mapped_column(String(50))  # "S. OGIER"
    full_name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(10))  # "OGI"

    # Optional fields
    license_number: Mapped[str | None] = mapped_column(String(50))
    state: Mapped[str | None] = mapped_column(String(50))

    # Polymorphic identity setup
    __mapper_args__ = {
        "polymorphic_on": person_type,
        "polymorphic_identity": PersonType.PERSON,
    }


class Driver(Person):
    """Driver inherits all fields from Person, no separate table needed"""

    __mapper_args__ = {
        "polymorphic_identity": PersonType.DRIVER,
    }


class CoDriver(Person):
    """CoDriver inherits all fields from Person, no separate table needed"""

    __mapper_args__ = {
        "polymorphic_identity": PersonType.CODRIVER,
    }
