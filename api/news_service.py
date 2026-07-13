import feedparser
import httpx
import logging
from typing import List
from datetime import datetime, timedelta, timezone
from time import mktime
import traceback
import re
import asyncio

from models.news import NewsArticle

logger = logging.getLogger(__name__)

# Dictionary of RSS feeds for each category and language
FEEDS = {
    "wrc": {
        "en": {"url": "https://dirtfish.com/feed/", "source": "DirtFish"},
        "pt": {"url": "https://www.autosport.pt/tag/wrc/feed/", "source": "AutoSport"}
    },
    "f1": {
        "en": {"url": "https://www.motorsport.com/rss/f1/news/", "source": "Motorsport.com"},
        "pt": {"url": "https://www.autosport.pt/tag/f1/feed/", "source": "AutoSport"}
    }
}

def _get_image_from_entry(entry):
    """Helper to find an image URL within a feed entry."""
    if 'media_content' in entry and entry.media_content:
        return entry.media_content[0]['url']
    if 'links' in entry:
        for link in entry.links:
            if link.get('type', '').startswith('image/'):
                return link.href
    if 'enclosures' in entry:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image/'):
                return enc.href
                
    html_content = ""
    if 'content' in entry and entry.content:
        html_content += entry.content[0].value
    if 'summary' in entry:
        html_content += entry.summary
        
    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html_content)
    if img_match:
        return img_match.group(1)
        
    return None

async def _fetch_og_image(client: httpx.AsyncClient, article: NewsArticle):
    """Fallback to scrape og:image from the article's actual webpage if RSS doesn't provide one."""
    if article.image_url is not None:
        return
    try:
        r = await client.get(article.link, timeout=5.0)
        match = re.search(r'<meta property="og:image" content="([^"]+)"', r.text)
        if match:
            article.image_url = match.group(1)
    except Exception as e:
        logger.debug(f"Failed to fetch og:image for {article.link}: {e}")

async def fetch_news_from_feed(category: str, language: str = "en") -> List[NewsArticle]:
    """
    Fetches and parses news from a given RSS feed URL, returning only articles
    from the last 7 days.
    """
    category = category.lower()
    language = language.lower()

    if category not in FEEDS or language not in FEEDS[category]:
        logger.warning(f"No feed found for category '{category}' and language '{language}'")
        return []

    feed_info = FEEDS[category][language]
    url = feed_info["url"]
    source = feed_info["source"]
    
    articles = []
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            logger.info(f"Fetching news for {category} ({language}) from {url}")
            response = await client.get(url, timeout=15.0)
            response.raise_for_status()
            
            feed = feedparser.parse(response.text)

            if feed.bozo:
                logger.warning(f"Feed for {category} ({language}) is malformed. Bozo exception: {feed.bozo_exception}")

            logger.info(f"Found {len(feed.entries)} entries in {category} ({language}) feed.")

            one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)

            for entry in feed.entries:
                try:
                    published_dt = datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
                    
                    if published_dt < one_week_ago:
                        continue

                    articles.append(
                        NewsArticle(
                            title=entry.title,
                            summary=entry.summary,
                            link=entry.link,
                            image_url=_get_image_from_entry(entry),
                            published_date=published_dt,
                            source=source
                        )
                    )
                except Exception as e:
                    logger.error(f"Failed to parse entry for {category}: {entry.get('title')}")
                    logger.error(f"Parse Error: {e}\n{traceback.format_exc()}")
                    continue
            
            # Fetch missing images (e.g. for DirtFish) concurrently
            tasks = [_fetch_og_image(client, article) for article in articles if article.image_url is None]
            if tasks:
                await asyncio.gather(*tasks)
        
        articles.sort(key=lambda x: x.published_date, reverse=True)
        logger.info(f"Returning {len(articles)} articles for {category} ({language}) after filtering.")
        return articles

    except Exception as e:
        logger.error(f"Error fetching or parsing RSS feed for {category} from {url}: {e}")
        return []
