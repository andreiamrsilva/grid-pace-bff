import asyncio
from ingestion.wrc_client import fetch_wrc_event_stages
from core.database_service import save_stages_to_db

async def main():
    stages = await fetch_wrc_event_stages(642)
    if stages:
        await save_stages_to_db(642, stages)
        print(f"Saved {len(stages)} stages for event 642.")
    else:
        print("No stages found.")

if __name__ == "__main__":
    asyncio.run(main())
