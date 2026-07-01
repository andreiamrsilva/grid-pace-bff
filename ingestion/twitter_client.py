import logging
import asyncio
from typing import List
from datetime import datetime, timezone, timedelta
import uuid
import os

from ntscraper import Nitter
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

def parse_twitter_date(date_str: str) -> datetime:
    """
    Parses dates from ntscraper, typically in format: 'Apr 11, 2024 · 2:03 PM UTC'
    """
    try:
        clean_date = date_str.replace(" ·", "")
        dt = datetime.strptime(clean_date, "%b %d, %Y %I:%M %p %Z")
        return dt.replace(tzinfo=timezone.utc)
    except Exception as e:
        twitter_logger.error(f"Failed to parse date string '{date_str}': {e}")
        return datetime.now(timezone.utc)

async def fetch_tweets_for_session(
    start_time: datetime, 
    end_time: datetime, 
    search_term: str = "from:OfficialWRC",
    source: TimelineEventSource = TimelineEventSource.WRC_SOCIAL_MEDIA,
    author_display: str = "@OfficialWRC"
) -> List[TimelineEvent]:
    """
    Uses ntscraper to search for tweets in a given time window.
    """
    events = []
    try:
        scraper = Nitter()
        since_date = start_time.strftime("%Y-%m-%d")
        until_date = (end_time + timedelta(days=1)).strftime("%Y-%m-%d")
        
        query = f"{search_term} since:{since_date} until:{until_date}"
        
        loop = asyncio.get_running_loop()
        def get_tweets_sync():
            return scraper.get_tweets(query, mode='term', number=50)
            
        result = await loop.run_in_executor(None, get_tweets_sync)
        
        if result and 'tweets' in result:
            for t in result['tweets']:
                tweet_time = parse_twitter_date(t.get('date', ''))
                # Precise time filtering
                if start_time <= tweet_time <= end_time:
                    text = t.get('text', '')
                    events.append(TimelineEvent(
                        id=str(uuid.uuid4()),
                        timestamp=tweet_time,
                        source=source,
                        severity=TimelineEventSeverity.INFO,
                        message=f"🐦 {author_display}: {text}",
                        metadata={
                            "tweet_url": t.get('link', ''),
                            "message_pt": f"🐦 {author_display}: {text}",
                            "message_en": f"🐦 {author_display}: {text}"
                        }
                    ))
    except Exception as e:
        twitter_logger.error(f"Failed to fetch tweets using ntscraper. Query: {search_term}. Error: {e}")
        
    return events
