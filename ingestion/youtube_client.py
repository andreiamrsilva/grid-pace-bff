import logging
import os
import uuid
from datetime import datetime

import aiohttp

from models.timeline import TimelineEvent, TimelineEventSource, TimelineEventSeverity

logger = logging.getLogger(__name__)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

import logging
import os
import uuid
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx
import aiohttp

from models.timeline import TimelineEvent, TimelineEventSource, TimelineEventSeverity

logger = logging.getLogger(__name__)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

# Official Channel IDs
WRC_CHANNEL_ID = "UC5G6kTnHXDz0WIBC2VGBOqg"
F1_CHANNEL_ID = "UC0R3-zRpeIVUnavcRTPWzZA"

def _build_youtube_timeline_event(title: str, video_id: str, thumbnail_url: str, pub_date: datetime = None) -> TimelineEvent:
    """Helper to build a deterministic YouTube TimelineEvent."""
    event_ts = pub_date if pub_date else datetime.now(timezone.utc)
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"yt_{video_id}"))
    
    return TimelineEvent(
        id=deterministic_id,
        timestamp=event_ts,
        source=TimelineEventSource.YOUTUBE,
        severity=TimelineEventSeverity.INFO,
        message=f"🎥 Destaques Oficiais Disponíveis: {title}",
        metadata={
            "video_url": video_url,
            "thumbnail_url": thumbnail_url,
            "media_type": "youtube_video",
            "message_pt": f"🎥 Destaques Oficiais Disponíveis: {title}",
            "message_en": f"🎥 Official Highlights Available: {title}"
        }
    )

async def search_youtube_rss_feed(channel_id: str, query_filter: str = "") -> list[TimelineEvent]:
    """Fetches public YouTube RSS video feed for a given channel ID without requiring an API key."""
    events = []
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                root = ET.fromstring(response.text)
                ns = {'atom': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
                entries = root.findall('atom:entry', ns)
                
                filter_terms = [t.lower() for t in query_filter.split() if len(t) > 2]
                
                for entry in entries:
                    title = entry.find('atom:title', ns).text or ""
                    video_id = entry.find('yt:videoId', ns).text or ""
                    pub_str = entry.find('atom:published', ns).text or ""
                    
                    if not video_id or not title:
                        continue
                        
                    # Filter by query terms if provided
                    title_lower = title.lower()
                    if filter_terms and not any(term in title_lower for term in filter_terms):
                        continue
                        
                    pub_date = None
                    if pub_str:
                        try:
                            pub_date = datetime.fromisoformat(pub_str)
                            if pub_date.tzinfo is None:
                                pub_date = pub_date.replace(tzinfo=timezone.utc)
                        except Exception:
                            pass
                            
                    thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                    events.append(_build_youtube_timeline_event(title, video_id, thumbnail_url, pub_date))
                    if len(events) >= 3:
                        break
    except Exception as e:
        logger.warning(f"Error fetching YouTube RSS feed for channel {channel_id}: {e}")
    return events

async def search_youtube_html(query: str) -> list[TimelineEvent]:
    """Scrapes YouTube search HTML for top matching videos without requiring an API key."""
    events = []
    q_encoded = urllib.parse.quote(query)
    url = f"https://www.youtube.com/results?search_query={q_encoded}"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                html = response.text
                video_matches = re.findall(r'\"videoRenderer\":\{\"videoId\":\"([a-zA-Z0-9_-]{11})\",\"thumbnail\":\{\"thumbnails\":\[\{\"url\":\"([^\"]+)\"', html)
                titles = re.findall(r'\"title\":\{\"runs\":\[\{\"text\":\"([^\"]+)\"\}', html)
                
                seen_ids = set()
                for i, (vid, thumb) in enumerate(video_matches):
                    if vid in seen_ids:
                        continue
                    seen_ids.add(vid)
                    
                    title = titles[i] if i < len(titles) else query
                    clean_thumb = thumb.replace(r"\u0026", "&")
                    events.append(_build_youtube_timeline_event(title, vid, clean_thumb))
                    if len(events) >= 2:
                        break
    except Exception as e:
        logger.warning(f"Error scraping YouTube HTML search for '{query}': {e}")
    return events

async def search_youtube_highlights(query: str, published_after: datetime = None, channel_id: str = None) -> list[TimelineEvent]:
    """
    Searches YouTube for highlight videos.
    Tries YouTube Data API first if YOUTUBE_API_KEY is configured,
    otherwise falls back to RSS feed parsing and HTML search.
    """
    # Fix invalid legacy channel IDs
    if channel_id == "UC5-51l67x6y2uT-1sPzWkYA":
        channel_id = WRC_CHANNEL_ID

    events = []

    # 1. Official YouTube API (if key is set)
    if YOUTUBE_API_KEY:
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "key": YOUTUBE_API_KEY,
            "maxResults": 1,
            "order": "relevance"
        }
        if published_after:
            params["publishedAfter"] = published_after.strftime("%Y-%m-%dT%H:%M:%SZ")
        if channel_id:
            params["channelId"] = channel_id

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(YOUTUBE_SEARCH_URL, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        items = data.get("items", [])
                        if items:
                            item = items[0]
                            video_id = item["id"]["videoId"]
                            snippet = item["snippet"]
                            title = snippet["title"]
                            thumbnail_url = snippet["thumbnails"].get("high", {}).get("url", snippet["thumbnails"]["default"]["url"])
                            
                            pub_str = snippet.get("publishedAt")
                            pub_date = datetime.fromisoformat(pub_str.replace("Z", "+00:00")) if pub_str else None
                            events.append(_build_youtube_timeline_event(title, video_id, thumbnail_url, pub_date))
                            return events
                    else:
                        logger.warning(f"YouTube Data API status {response.status}. Attempting fallback...")
        except Exception as e:
            logger.warning(f"YouTube Data API call failed: {e}. Attempting fallback...")

    # 2. RSS Feed Fallback for known channel IDs
    target_channel = channel_id
    if not target_channel:
        query_lower = query.lower()
        if "wrc" in query_lower:
            target_channel = WRC_CHANNEL_ID
        elif "f1" in query_lower or "grand prix" in query_lower:
            target_channel = F1_CHANNEL_ID

    if target_channel:
        rss_events = await search_youtube_rss_feed(target_channel, query_filter=query)
        if rss_events:
            return rss_events

    # 3. HTML Search Fallback
    html_events = await search_youtube_html(query)
    return html_events

