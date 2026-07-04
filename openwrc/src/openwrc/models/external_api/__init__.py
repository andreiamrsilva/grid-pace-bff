"""
External API models with Api prefix for clarity.
"""

# Event models
from .event_models import (
    ApiSeason,
    ApiSeasonDetail,
    ApiSeasonRound,
    ApiSeasonEventInfo,
    ApiEventMetadata,
    ApiRallyMetadata,
    ApiEventClass,
    ApiCountryMetadata,
)

# Entry models
from .entry_models import (
    ApiPerson,
    ApiDriver,
    ApiCoDriver,
    ApiManufacturer,
    ApiEntrant,
    ApiGroup,
    ApiEntry,
    ApiRallyEntries,
    ApiStartList,
    ApiStartListItem,
)

# Itinerary models
from .itinerary_models import (
    ApiItinerary,
    ApiItineraryLeg,
    ApiItinerarySection,
    ApiStage,
    ApiControl,
)

# Result models
from .result_models import (
    ApiStageResults,
    ApiRallyResults,
    ApiSplitTimeResults,
    ApiStageTimeResults,
    ApiShakedownTimeResults,
    ApiResultEntry,
    ApiStageTimeEntry,
    ApiShakedownTimeEntry,
    ApiSplitTimeEntry,
)

__all__ = [
    # Event
    "ApiSeason",
    "ApiSeasonDetail",
    "ApiSeasonRound",
    "ApiSeasonEventInfo",
    "ApiEventMetadata",
    "ApiRallyMetadata",
    "ApiEventClass",
    "ApiCountryMetadata",
    # Entry
    "ApiPerson",
    "ApiDriver",
    "ApiCoDriver",
    "ApiManufacturer",
    "ApiEntrant",
    "ApiGroup",
    "ApiEntry",
    "ApiRallyEntries",
    "ApiStartList",
    "ApiStartListItem",
    # Itinerary
    "ApiItinerary",
    "ApiItineraryLeg",
    "ApiItinerarySection",
    "ApiStage",
    "ApiControl",
    # Results
    "ApiStageResults",
    "ApiRallyResults",
    "ApiSplitTimeResults",
    "ApiStageTimeResults",
    "ApiShakedownTimeResults",
    "ApiResultEntry",
    "ApiStageTimeEntry",
    "ApiShakedownTimeEntry",
    "ApiSplitTimeEntry",
]
