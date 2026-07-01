from typing import List, Optional
from fastapi import APIRouter, Query, Depends, Request
import logging
import asyncio

from models.news import NewsArticle
from api.news_service import fetch_news_from_feed
from core.redis_service import get_cached_data, set_cached_data

logger = logging.getLogger(__name__)

from core.security import verify_client_token, verify_app_check_token
from core.rate_limit import limiter

router = APIRouter(
    prefix="/news",
    tags=["news"],
    dependencies=[Depends(verify_client_token), Depends(verify_app_check_token)],
)

CACHE_TTL_SECONDS = 900 # 15 minutes

@router.get("", response_model=List[NewsArticle])
@limiter.limit("60/minute")
async def get_news(
    request: Request,
    categories: List[str] = Query(..., description="A list of categories (e.g., WRC, F1) to fetch news for."),
    language: str = Query("en", description="Language for the news articles (e.g., 'en', 'pt'). Defaults to 'en'.")
):
    """
    Get the latest news articles for one or more categories.
    Results are cached for 15 minutes.
    """
    
    async def get_news_for_category(category: str):
        # Include language in the cache key to store different versions
        redis_key = f"news:{category.lower()}:{language.lower()}"
        
        cached_news = await get_cached_data(redis_key)
        if cached_news:
            logger.debug(f"Cache HIT for news: {redis_key}")
            return [NewsArticle(**article) for article in cached_news]

        logger.debug(f"Cache MISS for news: {redis_key}. Fetching from source.")
        
        articles = await fetch_news_from_feed(category, language)
        
        if articles:
            await set_cached_data(redis_key, [article.model_dump(mode='json') for article in articles], expiration_seconds=CACHE_TTL_SECONDS)
            
        return articles

    tasks = [get_news_for_category(cat) for cat in categories]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Combine and sort all articles from all categories
    all_articles = []
    for res in results:
        if isinstance(res, list):
            all_articles.extend(res)
    
    # Sort the final combined list by date
    all_articles.sort(key=lambda x: x.published_date, reverse=True)
    
    return all_articles
