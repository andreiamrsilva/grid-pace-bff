from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./historic_events.db"
    
    # Redis Cache
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # APIs
    OPENF1_API_URL: str = "https://api.openf1.org/v1"
    ERGAST_API_URL: str = "https://api.jolpi.ca/ergast/f1"
    
    # Security
    CRON_SECRET: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
