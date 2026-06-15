from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import asyncio
from api.routers import calendar, events
from api.database_service import init_db, archive_past_years
from api.routers.calendar import fetch_wrc_events_for_years
import os

async def daily_historic_updater():
    """Runs the historic archiver once a day."""
    while True:
        # Sleep for 24 hours (86400 seconds)
        await asyncio.sleep(86400)
        try:
            print("Running daily historic database update...")
            await archive_past_years(fetch_wrc_events_for_years)
        except Exception as e:
            print(f"Error in daily historic update: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup
    print("Server starting up...")
    
    # 1. Initialize the database
    init_db()
    
    # 2. Run the archiver on startup to catch up on any missing data
    asyncio.create_task(archive_past_years(fetch_wrc_events_for_years))
    
    # 3. Start the daily task to keep historic data updated (e.g. for new years or retrying failed records)
    app.state.daily_historic_task = asyncio.create_task(daily_historic_updater())
    
    # 4. Populate the recent cache for the first time
    await calendar.update_recent_cache()
    
    # 5. Start the periodic task to keep the recent cache fresh
    app.state.cache_updater_task = asyncio.create_task(calendar.periodic_cache_updater())
    
    yield
    
    # On shutdown
    print("Server shutting down...")
    app.state.cache_updater_task.cancel()
    app.state.daily_historic_task.cancel()
    try:
        await app.state.cache_updater_task
        await app.state.daily_historic_task
    except asyncio.CancelledError:
        print("Background tasks cancelled successfully.")

app = FastAPI(title="Grid Pace BFF API", lifespan=lifespan)

# Mount the logos directory
if os.path.exists("logos"):
    app.mount("/logos", StaticFiles(directory="logos"), name="logos")
else:
    print("Warning: 'logos' directory not found. Logo images will not be served.")

app.include_router(calendar.router)
app.include_router(events.router)

@app.get("/")
async def root():
    return {"message": "Welcome to Grid Pace BFF API"}
