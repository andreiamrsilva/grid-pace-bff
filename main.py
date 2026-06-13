from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import asyncio
from api.routers import calendar, events
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup
    print("Server starting up...")
    # Start the periodic task to keep the cache fresh.
    # The first update will happen immediately on startup.
    app.state.cache_updater_task = asyncio.create_task(calendar.periodic_cache_updater())
    
    yield
    
    # On shutdown
    print("Server shutting down...")
    app.state.cache_updater_task.cancel()
    try:
        await app.state.cache_updater_task
    except asyncio.CancelledError:
        print("Cache updater task cancelled successfully.")

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
