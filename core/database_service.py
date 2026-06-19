import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import Column, Integer, String, Date, MetaData, Table, update, Float, Boolean, DateTime, select
from datetime import datetime
from typing import List, Optional
import logging

from models.calendar import CalendarEvent
from models.event import Stage
from models.stage_times import StageStandings, DriverTime
from models.overall_standings import OverallStandings, OverallDriverStanding
from models.championship_standings import ChampionshipStandings, ChampionshipDriverStanding
from ingestion.openf1_client import get_openf1_calendar_events

from core.config import settings

engine = create_async_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

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

championship_standings_table = Table(
    'championship_standings', metadata,
    Column('id', Integer, primary_key=True),
    Column('year', Integer, index=True),
    Column('category', String, index=True),
    Column('position', Integer, nullable=True),
    Column('driver_name', String),
    Column('team_name', String, nullable=True),
    Column('logo_path', String, nullable=True),
    Column('points', Float, nullable=True),
    Column('wins', Integer, nullable=True),
)

logger = logging.getLogger(__name__)

async def init_db():
    """Creates all database tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    logger.info("Database initialized.")

async def get_last_archived_year() -> int:
    async with AsyncSessionLocal() as db:
        stmt = select(events_table.c.start_date).order_by(events_table.c.start_date.desc()).limit(1)
        result = await db.execute(stmt)
        last_year = result.scalar()
        if last_year:
            return last_year.year
    return 2017

async def upsert_events(events_to_upsert: List[CalendarEvent]):
    if not events_to_upsert:
        return
    async with AsyncSessionLocal() as db:
        for event_data in events_to_upsert:
            stmt = select(events_table).where(events_table.c.id == event_data.id)
            result = await db.execute(stmt)
            existing = result.first()
            
            if existing:
                upd_stmt = update(events_table).where(events_table.c.id == event_data.id).values(**event_data.model_dump())
                await db.execute(upd_stmt)
            else:
                ins_stmt = events_table.insert().values(**event_data.model_dump())
                await db.execute(ins_stmt)
        await db.commit()

async def get_all_events_from_db() -> List[CalendarEvent]:
    async with AsyncSessionLocal() as db:
        stmt = select(events_table)
        result = await db.execute(stmt)
        return [CalendarEvent(**row._asdict()) for row in result.all()]

async def save_stages_to_db(event_id: int, stages: List[Stage]):
    async with AsyncSessionLocal() as db:
        await db.execute(stages_table.delete().where(stages_table.c.event_id == event_id))
        for stage_data in stages:
            ins_stmt = stages_table.insert().values(event_id=event_id, **stage_data.model_dump())
            await db.execute(ins_stmt)
        await db.commit()

async def get_stages_from_db(event_id: int) -> Optional[List[Stage]]:
    async with AsyncSessionLocal() as db:
        stmt = select(stages_table).where(stages_table.c.event_id == event_id).order_by(stages_table.c.number)
        result = await db.execute(stmt)
        rows = result.all()
        if rows:
            return [Stage(**row._asdict()) for row in rows]
        return None

async def save_stage_times_to_db(stage_id: int, standings: StageStandings):
    async with AsyncSessionLocal() as db:
        await db.execute(stage_times_table.delete().where(stage_times_table.c.stage_id == stage_id))
        for driver_time in standings.standings:
            ins_stmt = stage_times_table.insert().values(stage_id=stage_id, **driver_time.model_dump())
            await db.execute(ins_stmt)
        await db.commit()

async def get_stage_times_from_db(stage_id: int, event_id: int, category: str) -> Optional[StageStandings]:
    async with AsyncSessionLocal() as db:
        stmt = select(stage_times_table).where(stage_times_table.c.stage_id == stage_id).order_by(stage_times_table.c.position)
        result = await db.execute(stmt)
        rows = result.all()
        if rows:
            standings = [DriverTime(**row._asdict()) for row in rows]
            return StageStandings(stage_id=stage_id, event_id=event_id, category=category, is_live=False, standings=standings)
        return None

async def save_overall_standings_to_db(event_id: int, standings: OverallStandings):
    async with AsyncSessionLocal() as db:
        await db.execute(overall_standings_table.delete().where(overall_standings_table.c.event_id == event_id))
        for standing in standings.standings:
            ins_stmt = overall_standings_table.insert().values(event_id=event_id, **standing.model_dump())
            await db.execute(ins_stmt)
        await db.commit()

async def get_overall_standings_from_db(event_id: int, category: str) -> Optional[OverallStandings]:
    async with AsyncSessionLocal() as db:
        stmt = select(overall_standings_table).where(overall_standings_table.c.event_id == event_id).order_by(overall_standings_table.c.position)
        result = await db.execute(stmt)
        rows = result.all()
        if rows:
            standings = [OverallDriverStanding(**row._asdict()) for row in rows]
            return OverallStandings(event_id=event_id, category=category, standings=standings)
        return None

async def save_championship_standings_to_db(standings: ChampionshipStandings):
    async with AsyncSessionLocal() as db:
        await db.execute(championship_standings_table.delete().where(
            championship_standings_table.c.year == standings.year,
            championship_standings_table.c.category == standings.category
        ))
        for standing in standings.standings:
            ins_stmt = championship_standings_table.insert().values(
                year=standings.year,
                category=standings.category,
                **standing.model_dump()
            )
            await db.execute(ins_stmt)
        await db.commit()

async def get_championship_standings_from_db(year: int, category: str) -> Optional[ChampionshipStandings]:
    async with AsyncSessionLocal() as db:
        stmt = select(championship_standings_table).where(
            championship_standings_table.c.year == year,
            championship_standings_table.c.category == category
        ).order_by(championship_standings_table.c.position)
        result = await db.execute(stmt)
        rows = result.all()
        if rows:
            standings = [ChampionshipDriverStanding(**row._asdict()) for row in rows]
            return ChampionshipStandings(year=year, category=category, standings=standings)
        return None
