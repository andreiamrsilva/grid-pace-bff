import os
import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()

import logging
import asyncio
import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.routers import calendar, events, championship, news, timeline, users
from ingestion.router import router as cron_router
from core.database_service import init_db
from core.rate_limit import limiter

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
    await init_db()
    
    yield
    
    # On shutdown
    logger.info("Server shutting down...")

# --- FastAPI App ---

app = FastAPI(title="Grid Pace BFF API", lifespan=lifespan)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production to specific domains if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiting setup
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Mount the logos directory
if os.path.exists("logos"):
    app.mount("/logos", StaticFiles(directory="logos"), name="logos")
else:
    logger.warning("Warning: 'logos' directory not found. Logo images will not be served.")

app.include_router(calendar.router)
app.include_router(events.router)
app.include_router(championship.router)
app.include_router(news.router)
app.include_router(timeline.router)
app.include_router(cron_router)
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])

@app.get("/")
@limiter.limit("5/minute")
async def root(request: Request):
    return {"message": "Welcome to Grid Pace BFF API"}
