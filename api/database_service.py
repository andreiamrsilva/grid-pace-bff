import asyncio
from sqlalchemy import create_engine, Column, Integer, String, Date, MetaData, Table
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from typing import List
import logging

from models.calendar import CalendarEvent
from api.f1_client import get_f1_calendar_events

DATABASE_URL = "sqlite:///./historic_events.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

metadata = MetaData()

events_table = Table(
    'events', metadata,
    Column('id', Integer, primary_key=True, autoincrement=False),
    Column('name', String),
    Column('category', String),
    Column('country', String),
    Column('country_image_url', String, nullable=True),
    Column('start_date', Date),
    Column('finish_date', Date),
    Column('current_leader', String, nullable=True),
    Column('current_leader_logo_path', String, nullable=True),
)

logger = logging.getLogger(__name__)

def init_db():
    """Creates the database and table if they don't exist."""
    metadata.create_all(bind=engine)
    logger.info("Database initialized.")

def get_last_archived_year() -> int:
    """Finds the most recent year stored in the historic database."""
    db = SessionLocal()
    try:
        last_year = db.query(events_table.c.start_date).order_by(events_table.c.start_date.desc()).first()
        if last_year:
            return last_year[0].year
    finally:
        db.close()
    # Return a default start year if the DB is empty
    return 2017 # Start before the first year we want to fetch (2018)

async def archive_past_years(fetch_wrc_events_for_years_func):
    """
    Fetches all events from last archived year up to the previous year 
    and stores them in the database.
    We pass the fetch_wrc function as an argument to avoid circular imports.
    """
    last_archived_year = get_last_archived_year()
    current_year = datetime.now().year
    
    # We want to archive years up to the previous year
    years_to_archive = range(last_archived_year + 1, current_year)
    
    if not years_to_archive:
        logger.info("Historic database is already up to date.")
        return

    logger.info(f"Archiving events for years: {list(years_to_archive)}")
    
    # Fetch all events for the missing years
    wrc_task = fetch_wrc_events_for_years_func(list(years_to_archive))
    f1_tasks = [get_f1_calendar_events(year) for year in years_to_archive]
    
    results = await asyncio.gather(*([wrc_task] + f1_tasks), return_exceptions=True)
    
    all_events_to_archive = []
    for result in results:
        if isinstance(result, list):
            all_events_to_archive.extend(result)
        elif isinstance(result, Exception):
            logger.error(f"Error fetching data for archiving: {result}")

    # Save to database
    db = SessionLocal()
    try:
        for event_data in all_events_to_archive:
            # Check if event already exists
            existing = db.query(events_table).filter_by(id=event_data.id).first()
            if not existing:
                stmt = events_table.insert().values(**event_data.model_dump())
                db.execute(stmt)
        db.commit()
        logger.info(f"Successfully archived new events.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving events to database: {e}")
    finally:
        db.close()

def get_historic_events_from_db() -> List[CalendarEvent]:
    """Retrieves all events from the historic database."""
    db = SessionLocal()
    try:
        result = db.query(events_table).all()
        return [CalendarEvent(**row._asdict()) for row in result]
    finally:
        db.close()
