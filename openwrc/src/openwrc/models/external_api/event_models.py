from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from pydantic import ConfigDict, Field, model_validator
from pydantic_extra_types.timezone_name import TimeZoneName
from .base_external_model import WrcExternalApiBaseModel


class ApiSeason(WrcExternalApiBaseModel):
    season_id: int
    name: str = Field(description="Championship name e.g. 'World Rally Championship'")
    year: int


class ApiSeasonEventInfo(WrcExternalApiBaseModel):
    """
    Lightweight event summary returned inside season-detail rounds.
    Subset of ApiEventMetadata — no rally or class IDs.
    """

    model_config = ConfigDict(extra="ignore")

    event_id: int
    name: str
    slug: str
    country: "ApiCountryMetadata"
    location: str
    start_date: date
    finish_date: date
    time_zone_id: str  # Changed from TimeZoneName to str
    time_zone_name: str
    surfaces: str
    shakedown_count: int


class ApiSeasonRound(WrcExternalApiBaseModel):
    season_id: int
    event_id: int
    order: int = Field(description="Round number within the season")
    event: ApiSeasonEventInfo


class ApiSeasonDetail(WrcExternalApiBaseModel):
    """
    Full season catalog returned by /api/season-detail.json?seasonId={id}.
    Contains all rounds with basic event info — use to enumerate event IDs
    before fetching full ApiEventMetadata per event.
    """

    model_config = ConfigDict(extra="ignore")

    season_id: int
    name: str
    year: int
    season_rounds: list[ApiSeasonRound]


class ApiEventClass(WrcExternalApiBaseModel):
    # classes like RC1, RC2, etc.
    event_class_id: int
    event_id: int
    name: str = Field(description="Competition class name (e.g., RC1, RC2)")


class ApiRallyMetadata(WrcExternalApiBaseModel):
    # events can have more than one rally
    rally_id: int = Field(description="Unique identifier for this rally")
    event_id: int

    # each rally has its own itinerary
    itinerary_id: int
    name: str
    is_main: bool
    event_classes: list[ApiEventClass]


class ApiCountryMetadata(WrcExternalApiBaseModel):
    country_id: int
    name: str
    iso2: str = Field(max_length=2)
    iso3: str = Field(max_length=3)


def convert_to_utc(dt: datetime, tz: str) -> datetime:  # Changed tz type to str
    """
    the base model will always try to convert all times to utc.
    when a time is specified to be a local time, use this util to convert to utc
    """
    if dt.tzinfo and dt.tzinfo == timezone.utc:
        native = dt.replace(tzinfo=None)
        try:
            # Convert timezone name string to ZoneInfo object
            event_tz = ZoneInfo(str(tz))
            local = native.replace(tzinfo=event_tz)
            return local.astimezone(timezone.utc)
        except Exception:
            # If timezone is invalid, return as is, or handle as needed
            return dt
    return dt


class ApiEventMetadata(WrcExternalApiBaseModel):

    # default to allowing extra fields from external sources
    model_config = ConfigDict(extra="ignore")

    rallies: list[ApiRallyMetadata] = Field(min_length=1)
    event_classes: list[ApiEventClass] = Field(
        description="All competition classes in this event"
    )
    event_id: int

    country_id: int
    country: ApiCountryMetadata
    name: str = Field(description="Official event name")

    slug: str = Field(description="uri slug maybe useful for some requests")
    location: str
    start_date: datetime
    finish_date: datetime
    time_zone_id: str = Field(  # Changed from TimeZoneName to str
        description="IANA timezone identifier for event location"
    )
    time_zone_name: str

    surfaces: str  # TODO: enum it

    shakedown_count: int = Field(description="Number of shakedown stages")

    @model_validator(mode="after")
    def convert_start_finish_to_utc(self) -> "ApiEventMetadata":
        """we convert start and finish dates from local time to utc time for easier comparison"""
        self.start_date = convert_to_utc(self.start_date, self.time_zone_id)
        self.finish_date = convert_to_utc(self.finish_date, self.time_zone_id)
        return self