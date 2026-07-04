import asyncio
from core.redis_service import redis_client
async def main():
    await redis_client.delete("calendar:f1:2026")
if __name__ == "__main__":
    asyncio.run(main())
