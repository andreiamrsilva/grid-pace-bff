import logging
import os
import uuid
from datetime import datetime

import aiohttp

from models.timeline import TimelineEvent, TimelineEventSource, TimelineEventSeverity

logger = logging.getLogger(__name__)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

async def search_youtube_highlights(query: str, published_after: datetime = None) -> list[TimelineEvent]:
    """
    Pesquisa na YouTube Data API por vídeos de destaques usando a query fornecida.
    Retorna uma lista (normalmente com 1 item) de TimelineEvent pronto a ser injetado.
    """
    if not YOUTUBE_API_KEY:
        logger.error("YOUTUBE_API_KEY is not set.")
        return []

    events = []
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "key": YOUTUBE_API_KEY,
        "maxResults": 1,
        "order": "relevance"
    }
    
    if published_after:
        # YouTube API requer formato ISO 8601 (ex: 1970-01-01T00:00:00Z)
        params["publishedAfter"] = published_after.strftime("%Y-%m-%dT%H:%M:%SZ")

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
                        thumbnail_url = snippet["thumbnails"]["high"]["url"] if "high" in snippet["thumbnails"] else snippet["thumbnails"]["default"]["url"]
                        
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                        
                        from datetime import timezone
                        event = TimelineEvent(
                            id=str(uuid.uuid4()),
                            timestamp=datetime.now(timezone.utc),
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
                        events.append(event)
                else:
                    logger.error(f"YouTube API returned status {response.status}: {await response.text()}")
    except Exception as e:
        logger.error(f"Error fetching YouTube highlights: {e}")

    return events
