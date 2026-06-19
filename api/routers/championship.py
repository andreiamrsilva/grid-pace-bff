from typing import List, Optional
from fastapi import APIRouter, Query
import logging
import asyncio

from models.championship_standings import ChampionshipStandings, ChampionshipTeamStandings
from ingestion.wrc_client import fetch_wrc_championship_standings, fetch_wrc_team_championship_standings
from ingestion.openf1_client import fetch_f1_championship_standings, fetch_f1_team_championship_standings
from core.redis_service import get_cached_data, set_cached_data

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/championship",
    tags=["championship"],
)

async def _get_driver_standings_for_category(category: str, year: int) -> Optional[ChampionshipStandings]:
    """Helper function to get driver standings for a single category, with caching."""
    redis_key = f"championship:drivers:{category.lower()}:{year}"
    
    cached_standings = await get_cached_data(redis_key)
    if cached_standings:
        return ChampionshipStandings(**cached_standings)

    logger.debug(f"Cache MISS for driver standings: {redis_key}. Fetching from source.")
    
    standings_to_cache = None
    if category.lower() == "wrc":
        standings_to_cache = await fetch_wrc_championship_standings(year)
    elif category.lower() == "f1":
        standings_to_cache = await fetch_f1_championship_standings(year)
    
    if standings_to_cache and standings_to_cache.standings:
        await set_cached_data(redis_key, standings_to_cache.model_dump(mode='json'), expiration_seconds=86400)
        
    return standings_to_cache

async def _get_team_standings_for_category(category: str, year: int) -> Optional[ChampionshipTeamStandings]:
    """Helper function to get team standings for a single category, with caching."""
    redis_key = f"championship:teams:{category.lower()}:{year}"
    
    cached_standings = await get_cached_data(redis_key)
    if cached_standings:
        return ChampionshipTeamStandings(**cached_standings)

    logger.debug(f"Cache MISS for team standings: {redis_key}. Fetching from source.")
    
    standings_to_cache = None
    if category.lower() == "wrc":
        standings_to_cache = await fetch_wrc_team_championship_standings(year)
    elif category.lower() == "f1":
        standings_to_cache = await fetch_f1_team_championship_standings(year)
    
    if standings_to_cache and standings_to_cache.standings:
        await set_cached_data(redis_key, standings_to_cache.model_dump(mode='json'), expiration_seconds=86400)
        
    return standings_to_cache

@router.get("/drivers/{year}", response_model=List[ChampionshipStandings])
async def get_driver_championship_standings(
    year: int,
    categories: List[str] = Query(..., description="A list of categories (e.g., WRC, F1) to fetch standings for."),
):
    """
    Get the overall driver championship standings for a given year and one or more categories.
    """
    tasks = [_get_driver_standings_for_category(cat, year) for cat in categories]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    final_standings = [res for res in results if isinstance(res, ChampionshipStandings)]
    
    return final_standings

@router.get("/teams/{year}", response_model=List[ChampionshipTeamStandings])
async def get_team_championship_standings(
    year: int,
    categories: List[str] = Query(..., description="A list of categories (e.g., WRC, F1) to fetch standings for."),
):
    """
    Get the overall team/constructor championship standings for a given year and one or more categories.
    """
    tasks = [_get_team_standings_for_category(cat, year) for cat in categories]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    final_standings = [res for res in results if isinstance(res, ChampionshipTeamStandings)]
    
    return final_standings
