import logging
from typing import Optional, List
from models.track_info import TrackInfo, TrackFeature

logger = logging.getLogger(__name__)

# Mock database of track/stage information
TRACK_DB = [
    # WRC Iconic Stages
    TrackInfo(
        track_id="wrc_fafe",
        name="Fafe",
        category="WRC",
        is_iconic=True,
        description="One of the most famous stages in the World Rally Championship, known for its massive jumps and passionate crowds.",
        features=[
            TrackFeature(name="Pedra Sentada Jump", description="Iconic massive jump near the end of the stage."),
            TrackFeature(name="Gravel", description="Fast and flowing gravel surface.")
        ],
        length_km=11.18,
        surface="Gravel"
    ),
    TrackInfo(
        track_id="wrc_ouninpohja",
        name="Ouninpohja",
        category="WRC",
        is_iconic=True,
        description="Legendary Finnish stage characterized by blind crests, huge jumps, and extreme speeds.",
        features=[
            TrackFeature(name="Yellow House Jump", description="One of the most famous jumps in rallying."),
            TrackFeature(name="High Speed", description="Extremely fast average speeds.")
        ],
        length_km=32.98,
        surface="Gravel"
    ),
    TrackInfo(
        track_id="wrc_col_de_turini",
        name="Col de Turini",
        category="WRC",
        is_iconic=True,
        description="Famous mountain pass stage in Rallye Monte-Carlo, often driven at night with unpredictable snow/ice.",
        features=[
            TrackFeature(name="Night Stage", description="Traditionally driven in the dark."),
            TrackFeature(name="Mixed Surface", description="Tarmac that is often covered in ice or snow.")
        ],
        length_km=31.0,
        surface="Tarmac/Ice/Snow"
    ),

    # F1 Circuits
    TrackInfo(
        track_id="f1_monaco",
        name="Circuit de Monaco",
        category="F1",
        is_iconic=True,
        description="The crown jewel of the F1 calendar. A tight, twisty street circuit where overtaking is almost impossible and qualifying is crucial.",
        features=[
            TrackFeature(name="Street Circuit", description="Narrow streets with no run-off areas."),
            TrackFeature(name="Fairmont Hairpin", description="The slowest corner in Formula 1.")
        ],
        length_km=3.337,
        corners=19,
        lap_record="1:12.909 (Lewis Hamilton, 2021)",
        surface="Tarmac"
    ),
    TrackInfo(
        track_id="f1_silverstone",
        name="Silverstone Circuit",
        category="F1",
        is_iconic=True,
        description="The historic home of British motorsport, featuring fast, flowing corner sequences like Maggotts and Becketts.",
        features=[
            TrackFeature(name="Maggotts & Becketts", description="Iconic sequence of high-speed corners."),
            TrackFeature(name="High Speed", description="Very fast and flowing layout.")
        ],
        length_km=5.891,
        corners=18,
        lap_record="1:27.097 (Max Verstappen, 2020)",
        surface="Tarmac"
    ),
    TrackInfo(
        track_id="f1_spa",
        name="Circuit de Spa-Francorchamps",
        category="F1",
        is_iconic=True,
        description="A driver favorite in the Ardennes forest, known for its extreme elevation changes and the legendary Eau Rouge/Raidillon complex.",
        features=[
            TrackFeature(name="Eau Rouge & Raidillon", description="World-famous uphill sweeping sequence."),
            TrackFeature(name="Longest Circuit", description="The longest lap on the current F1 calendar.")
        ],
        length_km=7.004,
        corners=19,
        lap_record="1:46.286 (Valtteri Bottas, 2018)",
        surface="Tarmac"
    )
]

async def enrich_track_info(name: str, category: str) -> Optional[TrackInfo]:
    """
    Looks up a track/stage by name and category (F1/WRC) and returns enriched TrackInfo if it's found in our local DB.
    Does a partial string match to handle variations in stage names (e.g. 'Fafe 1', 'Fafe 2').
    """
    if not name:
        return None

    name_lower = name.lower()
    
    for track in TRACK_DB:
        if track.category.upper() == category.upper():
            # For WRC, stages usually have numbers attached e.g., 'Fafe 1'
            if track.category == "WRC":
                if track.name.lower() in name_lower:
                    return track
            # For F1, we try to match part of the circuit name or city
            elif track.category == "F1":
                if track.name.lower() in name_lower or name_lower in track.name.lower():
                    return track

    return None

async def get_all_iconic_tracks(category: Optional[str] = None) -> List[TrackInfo]:
    """
    Returns all iconic tracks, optionally filtered by category.
    """
    if category:
        return [t for t in TRACK_DB if t.category.upper() == category.upper() and t.is_iconic]
    return [t for t in TRACK_DB if t.is_iconic]
