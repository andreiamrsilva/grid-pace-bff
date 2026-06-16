import asyncio
from sqlalchemy import create_engine, Column, Integer, String, Date, MetaData, Table, update, Float, Boolean, DateTime
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from typing import List, Optional
import logging

from models.calendar import CalendarEvent
from models.event import Stage
from models.stage_times import StageStandings, DriverTime
from models.overall_standings import OverallStandings, OverallDriverStanding
from api.openf1_client import get_openf1_calendar_events

DATABASE_URL = "sqlite:///./historic_events.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

metadata = MetaData()

# --- Table Definitions ---

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
    Column('status', String, default="Future event", nullable=False),
)

stages_table = Table(
    'stages', metadata,
    Column('id', Integer, primary_key=True, autoincrement=False),
    Column('event_id', Integer, index=True),
    Column('name', String),
    Column('number', Integer),
    Column('distance', Float, nullable=True),
    Column('start_time', DateTime, nullable=True),
    Column('status', String),
    Column('is_live', Boolean),
    Column('winner_name', String, nullable=True),
    Column('winner_logo_path', String, nullable=True),
    Column('winner_time', String, nullable=True),
)

stage_times_table = Table(
    'stage_times', metadata,
    Column('id', Integer, primary_key=True),
    Column('stage_id', Integer, index=True),
    Column('entry_id', Integer),
    Column('driver_name', String),
    Column('logo_path', String, nullable=True),
    Column('status', String),
    Column('time', String, nullable=True),
    Column('diff_to_first', String, nullable=True),
    Column('position', Integer, nullable=True),
    Column('last_split_id', Integer, nullable=True),
    Column('position_change', Integer, nullable=True),
)

overall_standings_table = Table(
    'overall_standings', metadata,
    Column('id', Integer, primary_key=True),
    Column('event_id', Integer, index=True),
    Column('position', Integer, nullable=True),
    Column('driver_name', String),
    Column('logo_path', String, nullable=True),
    Column('time', String, nullable=True),
    Column('diff_to_first', String, nullable=True),
    Column('points', Integer, nullable=True),
    Column('position_change', Integer, nullable=True),
)

logger = logging.getLogger(__name__)

def init_db():
    """Creates all database tables if they don't exist."""
    metadata.create_all(bind=engine)
    logger.info("Database initialized.")

# ... (rest of the functions are preserved)
def get_last_archived_year() -> int:
    db = SessionLocal()
    try:
        last_year = db.query(events_table.c.start_date).order_by(events_table.c.start_date.desc()).first()
        if last_year:
            return last_year[0].year
    finally:
        db.close()
    return 2017

async def _upsert_events(events_to_upsert: List[CalendarEvent]):
    db = SessionLocal()
    try:
        for event_data in events_to_upsert:
            existing = db.query(events_table).filter_by(id=event_data.id).first()
            if existing:
                stmt = update(events_table).where(events_table.c.id == event_data.id).values(**event_data.model_dump())
                db.execute(stmt)
            else:
                stmt = events_table.insert().values(**event_data.model_dump())
                db.execute(stmt)
        db.commit()
    finally:
        db.close()

async def archive_past_years(fetch_wrc_events_for_years_func):
    last_archived_year = get_last_archived_year()
    current_year = datetime.now().year
    years_to_archive = range(last_archived_year + 1, current_year)
    if not years_to_archive:
        return
    wrc_events = await fetch_wrc_events_for_years_func(list(years_to_archive))
    f1_events = []
    for year in years_to_archive:
        f1_events.extend(await get_openf1_calendar_events(year))
        await asyncio.sleep(2)
    await _upsert_events(wrc_events + f1_events)

async def update_current_year_events(fetch_wrc_events_for_years_func):
    current_year = datetime.now().year
    wrc_events = await fetch_wrc_events_for_years_func([current_year])
    f1_events = await get_openf1_calendar_events(current_year)
    await _upsert_events(wrc_events + f1_events)

def get_all_events_from_db() -> List[CalendarEvent]:
    db = SessionLocal()
    try:
        result = db.query(events_table).all()
        return [CalendarEvent(**row._asdict()) for row in result]
    finally:
        db.close()

def save_stages_to_db(event_id: int, stages: List[Stage]):
    db = SessionLocal()
    try:
        db.execute(stages_table.delete().where(stages_table.c.event_id == event_id))
        for stage_data in stages:
            stmt = stages_table.insert().values(event_id=event_id, **stage_data.model_dump())
            db.execute(stmt)
        db.commit()
    finally:
        db.close()

def get_stages_from_db(event_id: int) -> Optional[List[Stage]]:
    db = SessionLocal()
    try:
        result = db.query(stages_table).filter_by(event_id=event_id).order_by(stages_table.c.number).all()
        if result:
            return [Stage(**row._asdict()) for row in result]
        return None
    finally:
        db.close()

def save_stage_times_to_db(stage_id: int, standings: StageStandings):
    db = SessionLocal()
    try:
        db.execute(stage_times_table.delete().where(stage_times_table.c.stage_id == stage_id))
        for driver_time in standings.standings:
            stmt = stage_times_table.insert().values(stage_id=stage_id, **driver_time.model_dump())
            db.execute(stmt)
        db.commit()
    finally:
        db.close()

def get_stage_times_from_db(stage_id: int, event_id: int, category: str) -> Optional[StageStandings]:
    db = SessionLocal()
    try:
        result = db.query(stage_times_table).filter_by(stage_id=stage_id).order_by(stage_times_table.c.position).all()
        if result:
            standings = [DriverTime(**row._asdict()) for row in result]
            return StageStandings(stage_id=stage_id, event_id=event_id, category=category, is_live=False, standings=standings)
        return None
    finally:
        db.close()

def save_overall_standings_to_db(event_id: int, standings: OverallStandings):
    db = SessionLocal()
    try:
        db.execute(overall_standings_table.delete().where(overall_standings_table.c.event_id == event_id))
        for standing in standings.standings:
            stmt = overall_standings_table.insert().values(event_id=event_id, **standing.model_dump())
            db.execute(stmt)
        db.commit()
    finally:
        db.close()

def get_overall_standings_from_db(event_id: int, category: str) -> Optional[OverallStandings]:
    db = SessionLocal()
    try:
        result = db.query(overall_standings_table).filter_by(event_id=event_id).order_by(overall_standings_table.c.position).all()
        if result:
            standings = [OverallDriverStanding(**row._asdict()) for row in result]
            return OverallStandings(event_id=event_id, category=category, standings=standings)
        return None
    finally:
        db.close()
