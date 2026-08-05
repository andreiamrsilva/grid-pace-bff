import asyncio
import argparse
import sys
import os
import logging

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "openwrc", "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from ingestion.service import run_stage_times_repair

async def main():
    parser = argparse.ArgumentParser(description="Repair corrupted or legacy stage times in DB and Redis cache.")
    parser.add_argument("--event-id", type=int, default=None, help="Target event ID (e.g. 644 for WRC Finland). If omitted, repairs all events.")
    parser.add_argument("--category", type=str, default="wrc", help="Sport category ('wrc' or 'f1'). Defaults to 'wrc'.")
    
    args = parser.parse_args()
    logger.info(f"Starting stage times repair script with category='{args.category}', event_id={args.event_id}...")
    await run_stage_times_repair(event_id=args.event_id, category=args.category)
    logger.info("Stage times repair completed successfully.")

if __name__ == "__main__":
    asyncio.run(main())
