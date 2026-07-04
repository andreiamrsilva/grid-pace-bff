import asyncio
import httpx
from ingestion.openf1_client import get_f1_event_sessions, get_session_fastest_driver, OPENF1_API_URL

async def main():
    async with httpx.AsyncClient() as client:
        # fetch meetings for 2024 to find British GP
        meetings = await client.get(f"{OPENF1_API_URL}/meetings?year=2024")
        meetings_data = meetings.json()
        gb_gp = next((m for m in meetings_data if "British" in m['meeting_name']), None)
        if not gb_gp:
            print("British GP not found")
            return
        
        print(f"Meeting Key: 1289")
        sessions = await get_f1_event_sessions(1289)
        for s in sessions:
            print(f"Session {s.name} (Key: {s.id}), Winner: {s.winner_name}")

if __name__ == "__main__":
    asyncio.run(main())
