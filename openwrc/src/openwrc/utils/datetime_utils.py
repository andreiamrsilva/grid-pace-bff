"""
Datetime conversion utilities for WRC data.

All datetimes stored in the DB are UTC. Use these helpers to convert to an
event's local timezone (from EventMetadata.time_zone_id) or any IANA timezone.
"""

from datetime import datetime
from zoneinfo import ZoneInfo


def ms_to_time_str(ms: int | None) -> str | None:
    """Format a millisecond duration as H:MM:SS.s or MM:SS.s.

    Returns None when ms is None (e.g. retired driver with no time).
    Hours are only included when the duration is >= 1 hour.
    """
    if ms is None:
        return None
    total_tenths = ms // 100
    hours = total_tenths // 36000
    minutes = (total_tenths % 36000) // 600
    seconds = (total_tenths % 600) // 10
    tenths = total_tenths % 10
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}.{tenths}"
    return f"{minutes}:{seconds:02d}.{tenths}"


def to_tz(dt: datetime, tz: ZoneInfo) -> datetime:
    """Convert a UTC-aware datetime to the given timezone.

    Assumes dt is UTC. If dt is naive it is treated as UTC before converting.
    """
    utc = dt if dt.tzinfo is not None else dt.replace(tzinfo=ZoneInfo("UTC"))
    return utc.astimezone(tz)


def event_tz(time_zone_id: str) -> ZoneInfo:
    """Return the ZoneInfo for an event's IANA timezone string (e.g. 'Europe/Monaco')."""
    return ZoneInfo(time_zone_id)


def to_event_tz(dt: datetime, time_zone_id: str) -> datetime:
    """Convenience wrapper: convert a UTC datetime directly to the event's local time."""
    return to_tz(dt, event_tz(time_zone_id))
