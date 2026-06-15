import redis.asyncio as redis
import os
import logging
import json
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Try to get the Redis URL from the environment (useful for production)
# Fallback to localhost for local development with Docker
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create a global Redis connection pool
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

async def check_redis_connection() -> bool:
    """Checks if the Redis server is reachable."""
    try:
        await redis_client.ping()
        logger.info("Successfully connected to Redis.")
        return True
    except redis.ConnectionError as e:
        logger.error(f"Failed to connect to Redis at {REDIS_URL}. Make sure the Docker container is running. Error: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred while connecting to Redis: {e}")
        return False

async def get_cached_data(key: str) -> Optional[Any]:
    """Retrieves JSON data from Redis and deserializes it."""
    try:
        data_str = await redis_client.get(key)
        if data_str:
            return json.loads(data_str)
        return None
    except Exception as e:
        logger.error(f"Error reading key '{key}' from Redis: {e}")
        return None

async def set_cached_data(key: str, data: Any, expiration_seconds: Optional[int] = None) -> bool:
    """Serializes data to JSON and stores it in Redis with an optional expiration time."""
    try:
        data_str = json.dumps(data)
        if expiration_seconds:
            await redis_client.setex(key, expiration_seconds, data_str)
        else:
            await redis_client.set(key, data_str)
        return True
    except Exception as e:
        logger.error(f"Error writing key '{key}' to Redis: {e}")
        return False

async def close_redis_connection():
    """Closes the Redis connection pool."""
    await redis_client.close()
    logger.info("Redis connection closed.")
