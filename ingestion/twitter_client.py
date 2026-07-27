import asyncio
import calendar
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List

import feedparser

from models.timeline import TimelineEvent, TimelineEventSource, TimelineEventSeverity

# Setup specific logger for Twitter Scraper
twitter_logger = logging.getLogger("twitter_scraper")
twitter_logger.setLevel(logging.ERROR)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
if not twitter_logger.handlers:
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

TWITTER_API_IO_KEY = os.getenv("TWITTER_API_IO_KEY")

async def fetch_tweets_with_media(
    user_id: str, 
    start_time: datetime, 
    end_time: datetime,
    source: TimelineEventSource,
    author_display: str
) -> List[TimelineEvent]:
    """
    Fetches tweets from a specific user (by ID) using twitterapi.io and extracts those with video media.
    """
    import aiohttp
    
    if not TWITTER_API_IO_KEY:
        twitter_logger.error("TWITTER_API_IO_KEY is not set.")
        return []
        
    events = []
    # twitterapi.io endpoint for fetching a user's latest tweets
    url = f"https://api.twitterapi.io/twitter/user/last_tweets?userId={user_id}"
    headers = {
        "X-API-Key": TWITTER_API_IO_KEY
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    tweets = data.get("tweets", [])
                    
                    for tweet in tweets:
                        # Parse tweet created_at (format varies, usually ISO string or similar)
                        # Assume ISO for this example: "2024-05-10T14:32:00.000Z"
                        created_str = tweet.get("createdAt")
                        if not created_str:
                            continue
                            
                        # Parse tweet created_at which can be ISO or 'Mon Jul 27 15:31:00 +0000 2026'
                        try:
                            tweet_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                        except ValueError:
                            try:
                                tweet_dt = datetime.strptime(created_str, '%a %b %d %H:%M:%S %z %Y')
                            except ValueError:
                                # Fallback parse or skip
                                continue
                            
                        if start_time <= tweet_dt <= end_time:
                            # Check for media (video)
                            media_list = tweet.get("media", [])
                            video_media = next((m for m in media_list if m.get("type") in ["video", "animated_gif"]), None)
                            
                            if video_media:
                                video_url = video_media.get("videoUrl") or video_media.get("url")
                                thumbnail_url = video_media.get("previewImageUrl") or ""
                                text = tweet.get("text", "")
                                
                                event_id = tweet.get("id", str(uuid.uuid4()))
                                events.append(TimelineEvent(
                                    id=event_id,
                                    timestamp=tweet_dt,
                                    source=source,
                                    severity=TimelineEventSeverity.INFO,
                                    message=f"🎥 {author_display}: {text[:50]}...",
                                    metadata={
                                        "video_url": video_url,
                                        "thumbnail_url": thumbnail_url,
                                        "media_type": "twitter_video",
                                        "tweet_url": tweet.get("url", ""),
                                        "message_pt": f"🎥 {author_display}: {text}",
                                        "message_en": f"🎥 {author_display}: {text}"
                                    }
                                ))
                else:
                    twitter_logger.error(f"twitterapi.io returned status {response.status}: {await response.text()}")
    except Exception as e:
        twitter_logger.error(f"Error fetching tweets with media for user {user_id}: {e}")
        
    return events
