import logging
import asyncio
from typing import List
from datetime import datetime, timezone, timedelta
import uuid
import os
import time
import calendar
import feedparser

from models.timeline import TimelineEvent, TimelineEventSource, TimelineEventSeverity

# Setup specific logger for Twitter Scraper
log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
os.makedirs(log_dir, exist_ok=True)
twitter_logger = logging.getLogger("twitter_scraper")
twitter_logger.setLevel(logging.ERROR)
handler = logging.FileHandler(os.path.join(log_dir, "twitter_scraper_errors.log"))
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
twitter_logger.addHandler(handler)

RSS_MAPPING = {
    "from:OfficialWRC": "https://dirtfish.com/rally/wrc/feed/",
    "from:F1": "https://www.motorsport.com/rss/f1/news/"
}

async def fetch_tweets_for_session(
    start_time: datetime, 
    end_time: datetime, 
    search_term: str = "from:OfficialWRC",
    source: TimelineEventSource = TimelineEventSource.WRC_SOCIAL_MEDIA,
    author_display: str = "@OfficialWRC"
) -> List[TimelineEvent]:
    """
    Uses RSS Feeds to search for news in a given time window, maintaining the old method signature for compatibility.
    """
    events = []
    try:
        rss_url = RSS_MAPPING.get(search_term)
        if not rss_url:
            twitter_logger.error(f"No RSS feed mapping found for search_term: {search_term}")
            return events

        loop = asyncio.get_running_loop()
        def get_rss_sync():
            return feedparser.parse(rss_url)
            
        result = await loop.run_in_executor(None, get_rss_sync)
        
        if result and hasattr(result, 'entries'):
            for entry in result.entries:
                # parsed date is time.struct_time
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    ts = calendar.timegm(entry.published_parsed)
                    dt = datetime.fromtimestamp(ts, timezone.utc)
                else:
                    dt = datetime.now(timezone.utc)
                    
                # Precise time filtering
                if start_time <= dt <= end_time:
                    title = getattr(entry, 'title', '')
                    link = getattr(entry, 'link', '')
                    deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{link}_{title}"))
                    events.append(TimelineEvent(
                        id=deterministic_id,
                        timestamp=dt,
                        source=source,
                        severity=TimelineEventSeverity.INFO,
                        message=f"📰 {title}",
                        metadata={
                            "url": link,
                            "message_pt": f"📰 {title}",
                            "message_en": f"📰 {title}"
                        }
                    ))
    except Exception as e:
        twitter_logger.error(f"Failed to fetch RSS feeds. Query/Term: {search_term}. Error: {e}")
        
    return events
