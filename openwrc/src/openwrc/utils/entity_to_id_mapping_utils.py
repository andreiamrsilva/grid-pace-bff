from openwrc.models.db.entities import Person
from openwrc.models.db.event import Entry
from openwrc.models.db.itinerary import Stage


def map_driver_name_to_entry_id(
    entries: list[Entry], drivers: list[Person]
) -> dict[str, int]:
    """Build a case-insensitive lookup from driver name variants to entry_id.

    Indexes each driver by last name, full name, abbreviated name, and code so
    that inputs like "evans", "elfyn evans", "e. evans", or "EVA" all resolve
    to the correct entry_id.

    If multiple entries share the same driver (shouldn't happen within a rally)
    the last one wins.
    """
    driver_by_id = {d.person_id: d for d in drivers}
    result: dict[str, int] = {}
    for entry in entries:
        driver = driver_by_id.get(entry.driver_id)
        if driver is None:
            continue
        for name in (driver.last_name, driver.full_name, driver.abbv_name, driver.code):
            if name:
                result[name.lower()] = entry.entry_id
    return result


def map_stage_code_to_stage_id(stages: list[Stage]) -> dict[str, int]:
    """Build a case-insensitive lookup from stage code to stage_id.

    e.g. "ss1" / "SS1" → stage_id.
    """
    return {stage.code.lower(): stage.stage_id for stage in stages if stage.code}


def map_car_identifier_to_entry_id(entries: list[Entry]) -> dict[str, int]:
    """Build a lookup from car number string to entry_id.

    e.g. "1" / "69" → entry_id.
    """
    return {entry.identifier: entry.entry_id for entry in entries if entry.identifier}
