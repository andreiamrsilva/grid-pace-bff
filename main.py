import logging
import asyncio
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from api.routers import calendar, events, championship, news, cron
from api.database_service import init_db

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

# --- Lifespan Manager ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup
    logger.info("Server starting up...")
    
    # 1. Initialize the database
    init_db()
    
    yield
    
    # On shutdown
    logger.info("Server shutting down...")

# --- FastAPI App ---

app = FastAPI(title="Grid Pace BFF API", lifespan=lifespan)

# Mount the logos directory
if os.path.exists("logos"):
    app.mount("/logos", StaticFiles(directory="logos"), name="logos")
else:
    logger.warning("Warning: 'logos' directory not found. Logo images will not be served.")

app.include_router(calendar.router)
app.include_router(events.router)
app.include_router(championship.router)
app.include_router(news.router)
app.include_router(cron.router)

@app.get("/")
async def root():
    return {"message": "Welcome to Grid Pace BFF API"}
