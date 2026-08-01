import asyncio
import calendar
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
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

RSS_FEEDS = {
    "WRC": [
        "https://www.motorsport.com/rss/wrc/news/",
        "https://dirtfish.com/rally/wrc/feed/"
    ],
    "F1": [
        "https://www.motorsport.com/rss/f1/news/"
    ]
}

def detect_severity(text: str) -> TimelineEventSeverity:
    """Classifies timeline event severity based on keywords in title or body."""
    lower_text = text.lower()
    critical_keywords = [
        "crash", "accident", "red flag", "rolled", "stopped on track", 
        "hospital", "acidente", "bandeira vermelha", "capotou", "heavy crash"
    ]
    warning_keywords = [
        "puncture", "spin", "problem", "retired", "damage", "lost time",
        "pneu furado", "despiste", "problema", "danos", "abandono"
    ]
    
    if any(k in lower_text for k in critical_keywords):
        return TimelineEventSeverity.CRITICAL
    if any(k in lower_text for k in warning_keywords):
        return TimelineEventSeverity.WARNING
    return TimelineEventSeverity.INFO

async def fetch_rss_fallback_events(
    category: str, 
    start_time: datetime, 
    end_time: datetime, 
    source: TimelineEventSource
) -> List[TimelineEvent]:
    """Fetches news and updates from RSS feeds when Twitter API is unavailable."""
    import aiohttp
    events = []
    feeds = RSS_FEEDS.get(category.upper(), RSS_FEEDS["WRC"])
    
    # Expand window for news coverage
    window_start = start_time - timedelta(hours=12)
    window_end = end_time + timedelta(hours=6)
    
    try:
        async with aiohttp.ClientSession() as session:
            for feed_url in feeds:
                try:
                    async with session.get(feed_url, timeout=10) as response:
                        if response.status == 200:
                            content = await response.text()
                            parsed = feedparser.parse(content)
                            for entry in getattr(parsed, 'entries', []):
                                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                                    ts = calendar.timegm(entry.published_parsed)
                                    dt = datetime.fromtimestamp(ts, timezone.utc)
                                else:
                                    dt = datetime.now(timezone.utc)
                                    
                                if window_start <= dt <= window_end:
                                    title = getattr(entry, 'title', '')
                                    link = getattr(entry, 'link', '')
                                    summary = getattr(entry, 'summary', '')
                                    
                                    if not title:
                                        continue
                                        
                                    deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{link}_{title}"))
                                    severity = detect_severity(f"{title} {summary}")
                                    
                                    events.append(TimelineEvent(
                                        id=deterministic_id,
                                        timestamp=dt,
                                        source=source,
                                        severity=severity,
                                        message=f"📰 {title}",
                                        metadata={
                                            "url": link,
                                            "summary": summary[:200] if summary else "",
                                            "message_pt": f"📰 {title}",
                                            "message_en": f"📰 {title}"
                                        }
                                    ))
                except Exception as e:
                    twitter_logger.error(f"Error fetching RSS feed {feed_url}: {e}")
    except Exception as e:
        twitter_logger.error(f"Failed session creating RSS fallback: {e}")
        
    return events

async def fetch_tweets_with_media(
    user_id: str, 
    start_time: datetime, 
    end_time: datetime,
    source: TimelineEventSource,
    author_display: str
) -> List[TimelineEvent]:
    """
    Fetches social media posts and media from twitterapi.io or falls back to RSS news feeds.
    """
    import aiohttp
    category = "F1" if "f1" in str(source).lower() else "WRC"
    
    # Expand filter window to include pre/post stage posts & breaking news
    window_start = start_time - timedelta(hours=6) if start_time else datetime.now(timezone.utc) - timedelta(hours=24)
    window_end = end_time + timedelta(hours=6) if end_time else datetime.now(timezone.utc)
    
    if not TWITTER_API_IO_KEY:
        twitter_logger.warning("TWITTER_API_IO_KEY is not set. Using RSS news fallback.")
        return await fetch_rss_fallback_events(category, start_time, end_time, source)
        
    events = []
    url = f"https://api.twitterapi.io/twitter/user/last_tweets?userId={user_id}"
    headers = {
        "X-API-Key": TWITTER_API_IO_KEY
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=12) as response:
                if response.status == 200:
                    data = await response.json()
                    tweets = data.get("tweets", [])
                    
                    for tweet in tweets:
                        created_str = tweet.get("createdAt") or tweet.get("created_at")
                        if not created_str:
                            continue
                            
                        try:
                            tweet_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                        except ValueError:
                            try:
                                tweet_dt = datetime.strptime(created_str, '%a %b %d %H:%M:%S %z %Y')
                            except ValueError:
                                continue
                            
                        if window_start <= tweet_dt <= window_end:
                            text = tweet.get("text", "") or tweet.get("full_text", "")
                            event_id = str(tweet.get("id", uuid.uuid4()))
                            severity = detect_severity(text)
                            
                            # Check media (video or photo)
                            media_list = tweet.get("media", []) or tweet.get("extended_entities", {}).get("media", [])
                            video_media = next((m for m in media_list if m.get("type") in ["video", "animated_gif"]), None)
                            photo_media = next((m for m in media_list if m.get("type") in ["photo", "image"]), None)
                            
                            if video_media:
                                video_url = video_media.get("videoUrl") or video_media.get("url")
                                thumbnail_url = video_media.get("previewImageUrl") or ""
                                events.append(TimelineEvent(
                                    id=event_id,
                                    timestamp=tweet_dt,
                                    source=source,
                                    severity=severity,
                                    message=f"🎥 {author_display}: {text[:100]}...",
                                    metadata={
                                        "video_url": video_url,
                                        "thumbnail_url": thumbnail_url,
                                        "media_type": "twitter_video",
                                        "tweet_url": tweet.get("url", f"https://x.com/i/status/{event_id}"),
                                        "message_pt": f"🎥 {author_display}: {text}",
                                        "message_en": f"🎥 {author_display}: {text}"
                                    }
                                ))
                            elif photo_media:
                                image_url = photo_media.get("media_url_https") or photo_media.get("url") or ""
                                events.append(TimelineEvent(
                                    id=event_id,
                                    timestamp=tweet_dt,
                                    source=source,
                                    severity=severity,
                                    message=f"📷 {author_display}: {text[:100]}...",
                                    metadata={
                                        "image_url": image_url,
                                        "thumbnail_url": image_url,
                                        "media_type": "twitter_image",
                                        "tweet_url": tweet.get("url", f"https://x.com/i/status/{event_id}"),
                                        "message_pt": f"📷 {author_display}: {text}",
                                        "message_en": f"📷 {author_display}: {text}"
                                    }
                                ))
                            elif text:
                                events.append(TimelineEvent(
                                    id=event_id,
                                    timestamp=tweet_dt,
                                    source=source,
                                    severity=severity,
                                    message=f"💬 {author_display}: {text[:100]}...",
                                    metadata={
                                        "tweet_url": tweet.get("url", f"https://x.com/i/status/{event_id}"),
                                        "media_type": "twitter_post",
                                        "message_pt": f"💬 {author_display}: {text}",
                                        "message_en": f"💬 {author_display}: {text}"
                                    }
                                ))
                else:
                    twitter_logger.error(f"twitterapi.io returned status {response.status}. Falling back to RSS.")
                    return await fetch_rss_fallback_events(category, start_time, end_time, source)
    except Exception as e:
        twitter_logger.error(f"Error fetching tweets for user {user_id}: {e}. Falling back to RSS.")
        return await fetch_rss_fallback_events(category, start_time, end_time, source)
        
    if not events:
        twitter_logger.info("No tweets found in window. Attempting RSS fallback...")
        return await fetch_rss_fallback_events(category, start_time, end_time, source)
        
    return events

