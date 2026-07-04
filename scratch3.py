import asyncio
import httpx
from ingestion.openf1_client import OPENF1_API_URL

async def main():
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{OPENF1_API_URL}/drivers?session_key=latest")
        data = res.json()
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            for driver in data:
                if "Lawson" in driver.get('full_name', '') or "Lindblad" in driver.get('full_name', ''):
                    print(f"Driver: {driver['full_name']}, Team: {driver['team_name']}")
        else:
            print("Unexpected data:", data)

if __name__ == "__main__":
    asyncio.run(main())
