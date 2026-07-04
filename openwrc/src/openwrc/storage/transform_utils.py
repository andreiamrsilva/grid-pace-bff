from openwrc.models.external_api import (
    ApiControl,
    ApiCountryMetadata,
    ApiEntrant,
    ApiEventClass,
    ApiEventMetadata,
    ApiGroup,
    ApiItinerary,
    ApiItineraryLeg,
    ApiItinerarySection,
    ApiManufacturer,
    ApiRallyEntries,
    ApiRallyMetadata,
    ApiStage,
)


def transform_api_itinerary(
    api_response: ApiItinerary,
) -> tuple[
    list[ApiItineraryLeg],
    list[ApiItinerarySection],
    dict[int, list[ApiControl]],
    dict[int, list[ApiStage]],
]:
    legs: list[ApiItineraryLeg] = []
    sections: list[ApiItinerarySection] = []
    controls: dict[int, list[ApiControl]] = {}
    stages: dict[int, list[ApiStage]] = {}

    for leg in api_response.itinerary_legs:
        legs.append(leg)
        for section in leg.itinerary_sections:
            sections.append(section)
            controls[section.itinerary_section_id] = section.controls
            stages[section.itinerary_section_id] = section.stages
    return legs, sections, controls, stages


def transform_api_event_metadata(
    api_response: ApiEventMetadata,
) -> tuple[list[ApiRallyMetadata], list[ApiEventClass], dict[int, list[int]]]:
    event_class_ids = set(
        [event_class.event_class_id for event_class in api_response.event_classes]
    )
    event_classes = api_response.event_classes
    rally_to_class_ids: dict[int, list[int]] = {}

    for rally in api_response.rallies:
        rally_to_class_ids[rally.rally_id] = []
        for event_class in rally.event_classes:
            rally_to_class_ids[rally.rally_id].append(event_class.event_class_id)
            if event_class.event_class_id not in event_class_ids:
                event_class_ids.add(event_class.event_class_id)
                event_classes.append(event_class)
    return api_response.rallies, event_classes, rally_to_class_ids


def transform_api_entries(api_response: ApiRallyEntries):
    countries: dict[int, ApiCountryMetadata] = {}
    manufacturers: dict[int, ApiManufacturer] = {}
    entrants: dict[int, ApiEntrant] = {}
    groups: dict[int, ApiGroup] = {}

    drivers = []
    codrivers = []

    event_classes: dict[int, ApiEventClass] = {}
    entry_id_to_event_class_ids: dict[int, list[int]] = {}

    for entry in api_response:
        drivers.append(entry.driver)
        countries[entry.driver.country_id] = entry.driver.country
        codrivers.append(entry.codriver)
        countries[entry.codriver.country_id] = entry.codriver.country
        groups[entry.group.group_id] = entry.group
        manufacturers[entry.manufacturer.manufacturer_id] = entry.manufacturer
        entrants[entry.entrant.entrant_id] = entry.entrant

        entry_id_to_event_class_ids[entry.entry_id] = []
        for event_class in entry.event_classes:
            event_classes[event_class.event_class_id] = event_class
            entry_id_to_event_class_ids[entry.entry_id].append(
                event_class.event_class_id
            )
    return (
        countries.values(),
        manufacturers.values(),
        entrants.values(),
        groups.values(),
        drivers,
        codrivers,
        event_classes.values(),
        entry_id_to_event_class_ids,
    )
