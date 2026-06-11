from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
from api.routers import calendar, events

@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup
    print("Server starting up...")
    # Initial cache population
    asyncio.create_task(calendar.update_calendar_cache())
    # Start the periodic background task
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

app.include_router(calendar.router)
app.include_router(events.router)

@app.get("/")
async def root():
    return {"message": "Welcome to Grid Pace BFF API"}
