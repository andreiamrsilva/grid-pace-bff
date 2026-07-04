"""Models for rally entries (drivers, codrivers, cars) from WRC API"""

from datetime import datetime
from typing import Optional
from pydantic import Field, ConfigDict

from .base_external_model import WrcExternalApiBaseModel
from .event_models import ApiCountryMetadata, ApiEventClass


class ApiPerson(WrcExternalApiBaseModel):
    """Base model for driver or codriver"""

    model_config = ConfigDict(extra="ignore")

    person_id: int = Field(description="Unique identifier for this person")
    country_id: int
    country: ApiCountryMetadata

    season_id: Optional[int] = Field(default=None)
    event_id: Optional[int] = Field(default=None)
    external_id: Optional[str] = Field(default=None)

    # Name fields
    first_name: str
    last_name: str
    abbv_name: str = Field(description="Abbreviated name (e.g., S. OGIER)")
    full_name: str = Field(description="Full display name")
    code: str = Field(description="Three-letter code (e.g., OGI)")

    license_number: Optional[str] = Field(default=None)
    state: Optional[str] = Field(default="")


class ApiDriver(ApiPerson):
    """Driver information"""

    pass


class ApiCoDriver(ApiPerson):
    """Co-driver information"""

    pass


class ApiManufacturer(WrcExternalApiBaseModel):
    """Manufacturer/car brand information"""

    manufacturer_id: int = Field(description="Unique identifier for manufacturer")
    name: str = Field(description="Manufacturer name (e.g., Toyota, Hyundai)")
    logo_filename: Optional[str] = Field(
        default=None, description="Logo filename reference"
    )


class ApiEntrant(WrcExternalApiBaseModel):
    """Team/entrant information"""

    entrant_id: int = Field(description="Unique identifier for the team")
    name: str = Field(description="Team name (e.g., TOYOTA GAZOO RACING WRT)")
    logo_filename: Optional[str] = Field(
        default=None, description="Logo filename reference"
    )


class ApiGroup(WrcExternalApiBaseModel):
    """Competition group (Rally1, Rally2, etc.)"""

    group_id: int = Field(description="Unique identifier for this group")
    name: str = Field(description="Group name (e.g., Rally1, Rally2)")


class ApiEntry(WrcExternalApiBaseModel):
    """
    Complete entry for a driver/car/team combination in an event.
    This is the main unit that competes in rallies.
    """

    model_config = ConfigDict(extra="ignore")

    # Main identifiers
    entry_id: int = Field(description="Unique identifier for this entry")
    event_id: int

    # Related entities
    driver: ApiDriver
    codriver: ApiCoDriver
    manufacturer: ApiManufacturer
    entrant: ApiEntrant
    group: ApiGroup
    event_classes: list[ApiEventClass]

    # IDs for relationships
    driver_id: int
    codriver_id: int
    manufacturer_id: int
    entrant_id: int
    group_id: int

    # Entry details
    identifier: str = Field(description="Car number as string")
    vehicle_model: str = Field(description="Specific car model (e.g., GR Yaris Rally1)")
    entry_list_order: int = Field(description="Order in entry list")

    # Competition details
    eligibility: str = Field(description="Eligibility code (e.g., M for Manufacturer)")
    priority: str = Field(description="Priority classification (e.g., P1)")
    status: str = Field(description="Entry status (e.g., Entry, Retired)")
    tyre_manufacturer: str = Field(
        description="Tyre manufacturer name, seems to not be populated from api"
    )

    # Optional fields
    pbf: Optional[str] = Field(default=None)
    drive: Optional[str] = Field(default=None)
    tags: list[dict] = Field(default_factory=list)


# Type alias for list of entries
ApiRallyEntries = list[ApiEntry]


class ApiStartListItem(WrcExternalApiBaseModel):
    """A single entry in a start list with start time and order"""

    start_list_item_id: int = Field(
        description="Unique identifier for this start list item"
    )
    start_list_id: int = Field(description="Parent start list ID")
    entry_id: int = Field(description="Entry ID for this driver/car combination")
    start_date_time: datetime = Field(description="Start time in UTC")
    order: int = Field(description="Start order position")


class ApiStartList(WrcExternalApiBaseModel):
    """Complete start list for a leg"""

    start_list_items: list[ApiStartListItem] = Field(
        default_factory=list, description="All start list entries"
    )
    start_list_id: int = Field(description="Unique identifier for this start list")
    event_id: int = Field(description="Event ID")
    published_status: str = Field(description="Publication status (e.g., Published)")
    name: str = Field(description="Start list name (e.g., 'Thursday')")
