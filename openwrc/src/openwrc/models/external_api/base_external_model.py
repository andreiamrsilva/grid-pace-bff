from datetime import datetime, timezone
from pydantic import BaseModel, field_validator, model_validator, ConfigDict
from pydantic.alias_generators import to_camel

# Windows timezone name → IANA mapping.
# Older WRC API responses use Windows-style timezone names instead of IANA.
_WINDOWS_TO_IANA: dict[str, str] = {
    "Afghanistan Standard Time": "Asia/Kabul",
    "Arab Standard Time": "Asia/Riyadh",
    "Arabian Standard Time": "Asia/Dubai",
    "Argentina Standard Time": "America/Argentina/Buenos_Aires",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "Canada Central Standard Time": "America/Regina",
    "Cen. Australia Standard Time": "Australia/Adelaide",
    "Central America Standard Time": "America/Guatemala",
    "Central Asia Standard Time": "Asia/Almaty",
    "Central Brazilian Standard Time": "America/Cuiaba",
    "Central Europe Standard Time": "Europe/Budapest",
    "Central European Standard Time": "Europe/Warsaw",
    "Central Pacific Standard Time": "Pacific/Guadalcanal",
    "Central Standard Time": "America/Chicago",
    "Central Standard Time (Mexico)": "America/Mexico_City",
    "China Standard Time": "Asia/Shanghai",
    "E. Africa Standard Time": "Africa/Nairobi",
    "E. Australia Standard Time": "Australia/Brisbane",
    "E. Europe Standard Time": "Asia/Nicosia",
    "E. South America Standard Time": "America/Sao_Paulo",
    "Eastern Standard Time": "America/New_York",
    "Egypt Standard Time": "Africa/Cairo",
    "FLE Standard Time": "Europe/Helsinki",
    "GMT Standard Time": "Europe/London",
    "Greenland Standard Time": "America/Godthab",
    "GTB Standard Time": "Europe/Bucharest",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "India Standard Time": "Asia/Calcutta",
    "Israel Standard Time": "Asia/Jerusalem",
    "Jordan Standard Time": "Asia/Amman",
    "Korea Standard Time": "Asia/Seoul",
    "Middle East Standard Time": "Asia/Beirut",
    "Mountain Standard Time": "America/Denver",
    "Mountain Standard Time (Mexico)": "America/Chihuahua",
    "Myanmar Standard Time": "Asia/Rangoon",
    "N. Central Asia Standard Time": "Asia/Novosibirsk",
    "Namibia Standard Time": "Africa/Windhoek",
    "Nepal Standard Time": "Asia/Katmandu",
    "New Zealand Standard Time": "Pacific/Auckland",
    "Newfoundland Standard Time": "America/St_Johns",
    "North Asia East Standard Time": "Asia/Irkutsk",
    "North Asia Standard Time": "Asia/Krasnoyarsk",
    "Pacific SA Standard Time": "America/Santiago",
    "Pacific Standard Time": "America/Los_Angeles",
    "Pacific Standard Time (Mexico)": "America/Santa_Isabel",
    "Romance Standard Time": "Europe/Paris",
    "Russia Time Zone 11": "Asia/Kamchatka",
    "Russia Time Zone 3": "Europe/Samara",
    "Russian Standard Time": "Europe/Moscow",
    "SA Eastern Standard Time": "America/Cayenne",
    "SA Pacific Standard Time": "America/Bogota",
    "SA Western Standard Time": "America/La_Paz",
    "SE Asia Standard Time": "Asia/Bangkok",
    "Singapore Standard Time": "Asia/Singapore",
    "South Africa Standard Time": "Africa/Johannesburg",
    "Sri Lanka Standard Time": "Asia/Colombo",
    "Syria Standard Time": "Asia/Damascus",
    "Taipei Standard Time": "Asia/Taipei",
    "Tasmania Standard Time": "Australia/Hobart",
    "Tokyo Standard Time": "Asia/Tokyo",
    "Tonga Standard Time": "Pacific/Tongatapu",
    "Turkey Standard Time": "Europe/Istanbul",
    "US Eastern Standard Time": "America/Indianapolis",
    "US Mountain Standard Time": "America/Phoenix",
    "UTC": "UTC",
    "UTC+12": "Pacific/Fiji",
    "UTC-02": "America/Noronha",
    "UTC-11": "Pacific/Pago_Pago",
    "Ulaanbaatar Standard Time": "Asia/Ulaanbaatar",
    "Venezuela Standard Time": "America/Caracas",
    "W. Australia Standard Time": "Australia/Perth",
    "W. Central Africa Standard Time": "Africa/Lagos",
    "W. Europe Standard Time": "Europe/Berlin",
    "West Asia Standard Time": "Asia/Tashkent",
    "West Pacific Standard Time": "Pacific/Port_Moresby",
    "Yakutsk Standard Time": "Asia/Yakutsk",
}


class WrcExternalApiBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        alias_generator=to_camel,  # Convert snake_case fields to camelCase for API
        populate_by_name=True,  # Accept both snake_case and camelCase on input
    )

    @field_validator("time_zone_id", mode="before", check_fields=False)
    @classmethod
    def normalize_windows_timezone(cls, v: str) -> str:
        """Map Windows timezone names to IANA. Older WRC API responses use Windows-style names."""
        return _WINDOWS_TO_IANA.get(v, v)

    @model_validator(mode="after")
    def make_datetime_timezone_explicit(self) -> "WrcExternalApiBaseModel":
        for field_name, field_value in self.__dict__.items():
            if isinstance(field_value, datetime) and not field_value.tzinfo:
                setattr(self, field_name, field_value.replace(tzinfo=timezone.utc))
        return self
