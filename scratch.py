import asyncio
import sys
import os
sys.path.append(os.path.abspath("."))
sys.path.append(os.path.abspath("openWrc/src"))
from ingestion.wrc_client import fetch_wrc_events_for_years, fetch_wrc_overall_standings

async def main():
    events = await fetch_wrc_events_for_years([2026])
    acropolis = next((e for e in events if "Acropolis" in e.name), None)
    if not acropolis:
        print("Acropolis Rally not found.")
        return
    print(f"Event: {acropolis.name}, ID: {acropolis.id}, Leader: {acropolis.current_leader}")

    standings = await fetch_wrc_overall_standings(acropolis.id)
    if standings and standings.standings:
        print("Overall Standings Top 3:")
        for s in standings.standings[:3]:
            print(f"Pos {s.position}: {s.driver_name} (Time: {s.time})")

if __name__ == "__main__":
    asyncio.run(main())
