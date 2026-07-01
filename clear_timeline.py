import asyncio
from core.redis_service import redis_client

async def main():
    keys = await redis_client.keys("timeline:*")
    if keys:
        await redis_client.delete(*keys)
        print(f"Cleared {len(keys)} timeline keys from Redis.")
    else:
        print("No timeline keys found in Redis.")

if __name__ == "__main__":
    asyncio.run(main())
