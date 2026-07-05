import asyncio

from ingestion.openf1_client import get_f1_event_sessions


async def main():
    sessions = await get_f1_event_sessions(1289)
    for s in sessions:
        print(f"Session: {s.name}, Start: {s.start_time}, Status: {s.status}, is_live: {s.is_live}")

if __name__ == "__main__":
    asyncio.run(main())
