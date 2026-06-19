from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class NewsArticle(BaseModel):
    """Represents a single news article."""
    title: str
    summary: str
    link: str
    image_url: Optional[str] = None
    published_date: datetime
    source: str # e.g., "WRC", "Motorsport.com"
