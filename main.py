import logging
import asyncio
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from api.routers import calendar, events
from api.database_service import init_db, archive_past_years, update_current_year_events
from api.wrc_service import fetch_wrc_events_for_years # Changed import

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

# --- Background Tasks ---

async def daily_historic_archiver():
    """Archives past years once a day."""
    while True:
        await asyncio.sleep(86400) # 24 hours
        try:
            logger.info("Running daily historic database archive...")
            await archive_past_years(fetch_wrc_events_for_years)
        except Exception as e:
            logger.error(f"Error in daily historic archive: {e}")

async def frequent_current_year_updater():
    """Frequently updates the current year's events to catch new winners."""
    while True:
        try:
            logger.info("Running frequent update for current year events...")
            await update_current_year_events(fetch_wrc_events_for_years)
        except Exception as e:
            logger.error(f"Error in frequent current year update: {e}")
        await asyncio.sleep(900) # 15 minutes

# --- Lifespan Manager ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup
    logger.info("Server starting up...")
    
    # 1. Initialize the database
    init_db()
    
    # 2. Start background tasks
    app.state.historic_archiver_task = asyncio.create_task(daily_historic_archiver())
    app.state.current_year_updater_task = asyncio.create_task(frequent_current_year_updater())
    
    # 3. Run initial data population tasks on startup
    logger.info("Running initial database population...")
    asyncio.create_task(archive_past_years(fetch_wrc_events_for_years))
    asyncio.create_task(update_current_year_events(fetch_wrc_events_for_years))
    
    yield
    
    # On shutdown
    logger.info("Server shutting down...")
    app.state.historic_archiver_task.cancel()
    app.state.current_year_updater_task.cancel()
    try:
        await app.state.historic_archiver_task
        await app.state.current_year_updater_task
    except asyncio.CancelledError:
        logger.info("Background tasks cancelled successfully.")

# --- FastAPI App ---

app = FastAPI(title="Grid Pace BFF API", lifespan=lifespan)

# Mount the logos directory
if os.path.exists("logos"):
    app.mount("/logos", StaticFiles(directory="logos"), name="logos")
else:
    logger.warning("Warning: 'logos' directory not found. Logo images will not be served.")

app.include_router(calendar.router)
app.include_router(events.router)

@app.get("/")
async def root():
    return {"message": "Welcome to Grid Pace BFF API"}
