import asyncio

from ingestion.service import populate_historic_timeline


async def main():
    try:
        events = await populate_historic_timeline(11166)
        print(f"Success! {len(events)} events returned.")
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(main())
