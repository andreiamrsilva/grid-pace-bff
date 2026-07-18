import logging
from typing import List, Optional

from sqlalchemy import Column, Integer, String, Date, MetaData, Table, update, Float, Boolean, DateTime, select, JSON
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from core.config import settings
from models.calendar import CalendarEvent
from models.championship_standings import ChampionshipStandings, ChampionshipDriverStanding
from models.event import Stage
from models.overall_standings import OverallStandings, OverallDriverStanding
from models.stage_times import StageStandings, DriverTime
from models.timeline import TimelineEvent
from models.user import UserResponse, UserSettingsBase, UserSettingsUpdate, SubscriptionUpdate

db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+asyncpg://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

db_url = db_url.replace("&channel_binding=require", "")
db_url = db_url.replace("?channel_binding=require", "?")
db_url = db_url.replace("?&", "?")
if db_url.endswith("?"):
    db_url = db_url[:-1]

if "?sslmode=" in db_url:
    db_url = db_url.replace("?sslmode=", "?ssl=")
elif "&sslmode=" in db_url:
    db_url = db_url.replace("&sslmode=", "&ssl=")

if db_url.startswith("sqlite"):
    engine = create_async_engine(db_url, connect_args={"check_same_thread": False})
else:
    engine = create_async_engine(db_url)

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

timeline_events_table = Table(
    'timeline_events', metadata,
    Column('id', String, primary_key=True),
    Column('session_id', String, index=True),
    Column('timestamp', DateTime),
    Column('source', String),
    Column('severity', String),
    Column('message', String),
    Column('driver_number', String, nullable=True),
    Column('driver_name', String, nullable=True),
    Column('metadata', JSON, nullable=True),
)

users_table = Table(
    'users', metadata,
    Column('id', String, primary_key=True),  # Firebase UID
    Column('email', String, nullable=True),
    Column('is_eternal_pro', Boolean, default=False),
    Column('subscription_active', Boolean, default=False),
    Column('subscription_expires_at', DateTime, nullable=True),
)

user_settings_table = Table(
    'user_settings', metadata,
    Column('user_id', String, primary_key=True),
    Column('categories', JSON, nullable=True),
    Column('notif_stage_live', Boolean, default=True),
    Column('notif_stage_comments', Boolean, default=True),
)

logger = logging.getLogger(__name__)

async def init_db():
    """Database initialization is now handled by Alembic migrations."""
    logger.info("Database schema is now managed by Alembic. Run 'alembic upgrade head' to apply migrations.")

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

async def get_event_by_id_from_db(event_id: int) -> Optional[CalendarEvent]:
    async with AsyncSessionLocal() as db:
        stmt = select(events_table).where(events_table.c.id == event_id)
        result = await db.execute(stmt)
        row = result.first()
        if row:
            return CalendarEvent(**row._asdict())
        return None

async def save_stages_to_db(event_id: int, stages: List[Stage]):
    from sqlalchemy.exc import IntegrityError
    # Remove any duplicates in the incoming list first (based on stage ID)
    unique_stages = {s.id: s for s in stages}.values()
    
    async with AsyncSessionLocal() as db:
        try:
            await db.execute(stages_table.delete().where(stages_table.c.event_id == event_id))
            for stage_data in unique_stages:
                dump_data = stage_data.model_dump(exclude={"event_id"})
                # Remove tzinfo to avoid asyncpg offset-naive vs offset-aware error
                if dump_data.get('start_time') and dump_data['start_time'].tzinfo:
                    dump_data['start_time'] = dump_data['start_time'].replace(tzinfo=None)
                ins_stmt = stages_table.insert().values(event_id=event_id, **dump_data)
                await db.execute(ins_stmt)
            await db.commit()
        except IntegrityError as e:
            await db.rollback()
            logger.warning(f"IntegrityError while saving stages for event {event_id}. Likely a concurrent insert. Error: {e}")
        except Exception as e:
            await db.rollback()
            logger.error(f"Error saving stages for event {event_id}: {e}")

async def get_stages_from_db(event_id: int) -> Optional[List[Stage]]:
    async with AsyncSessionLocal() as db:
        stmt = select(stages_table).where(stages_table.c.event_id == event_id).order_by(stages_table.c.number)
        result = await db.execute(stmt)
        rows = result.all()
        if rows:
            return [Stage(**row._asdict()) for row in rows]
        return None

async def get_stage_by_id_from_db(stage_id: int) -> Optional[Stage]:
    async with AsyncSessionLocal() as db:
        stmt = select(stages_table).where(stages_table.c.id == stage_id)
        result = await db.execute(stmt)
        row = result.first()
        if row:
            return Stage(**row._asdict())
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

async def save_timeline_events_to_db(session_id: str, events: List[TimelineEvent]):
    if not events:
        return
    async with AsyncSessionLocal() as db:
        # For simplicity, we can do an insert or ignore / replace logic
        # Or delete existing for the session and insert all. Since events might update,
        # replace or insert might be better. Let's delete for session and insert.
        await db.execute(timeline_events_table.delete().where(timeline_events_table.c.session_id == str(session_id)))
        
        for event in events:
            # We dump to dict, but ensure enum types are strings, so mode='json'
            event_data = event.model_dump(mode='json')
            # Add session_id explicitly
            event_data['session_id'] = str(session_id)
            
            # Since model_dump(mode='json') converts timestamp to string, we need to convert it back to datetime for SQLAlchemy
            # if we defined the column as DateTime. The easiest is to use the original object values for DateTime.
            event_data_typed = event.model_dump()
            event_data_typed['session_id'] = str(session_id)
            
            # Remove tzinfo to avoid asyncpg offset-naive vs offset-aware error with TIMESTAMP WITHOUT TIME ZONE
            if event_data_typed.get('timestamp') and event_data_typed['timestamp'].tzinfo:
                event_data_typed['timestamp'] = event_data_typed['timestamp'].replace(tzinfo=None)
            
            ins_stmt = timeline_events_table.insert().values(**event_data_typed)
            await db.execute(ins_stmt)
            
        await db.commit()

async def get_timeline_events_from_db(session_id: str) -> List[TimelineEvent]:
    async with AsyncSessionLocal() as db:
        stmt = select(timeline_events_table).where(timeline_events_table.c.session_id == str(session_id)).order_by(timeline_events_table.c.timestamp)
        result = await db.execute(stmt)
        rows = result.all()
        events = []
        for row in rows:
            row_dict = row._asdict()
            # session_id is not in the model, pop it
            row_dict.pop('session_id', None)
            events.append(TimelineEvent(**row_dict))
        return events

async def get_or_create_user(uid: str, email: Optional[str] = None) -> UserResponse:
    async with AsyncSessionLocal() as db:
        # Check if user exists
        stmt = select(users_table).where(users_table.c.id == uid)
        result = await db.execute(stmt)
        user_row = result.first()
        
        if not user_row:
            # Create user
            ins_user = users_table.insert().values(id=uid, email=email)
            await db.execute(ins_user)
            
            # Create default settings
            ins_settings = user_settings_table.insert().values(
                user_id=uid,
                categories=[], # Default empty or default categories
                notif_stage_live=True,
                notif_stage_comments=True
            )
            await db.execute(ins_settings)
            await db.commit()
            
            # Fetch again to have the fully typed row
            result = await db.execute(stmt)
            user_row = result.first()
            
        # Get settings
        stmt_settings = select(user_settings_table).where(user_settings_table.c.user_id == uid)
        result_settings = await db.execute(stmt_settings)
        settings_row = result_settings.first()
        
        user_dict = user_row._asdict()
        # Rename id to uid for pydantic
        user_dict['uid'] = user_dict.pop('id')
        
        settings_dict = settings_row._asdict() if settings_row else {}
        settings_dict.pop('user_id', None)
        if settings_dict.get('categories') is None:
            settings_dict['categories'] = []
            
        user_response = UserResponse(**user_dict, settings=UserSettingsBase(**settings_dict))
        return user_response

async def update_user_settings_in_db(uid: str, settings_update: UserSettingsUpdate) -> UserSettingsBase:
    async with AsyncSessionLocal() as db:
        update_data = settings_update.model_dump(exclude_unset=True, mode='json')
        if not update_data:
            # Nothing to update, just return current settings
            stmt = select(user_settings_table).where(user_settings_table.c.user_id == uid)
            result = await db.execute(stmt)
            settings_row = result.first()
            settings_dict = settings_row._asdict() if settings_row else {}
            if settings_dict.get('categories') is None:
                settings_dict['categories'] = []
            return UserSettingsBase(**settings_dict)

        upd_stmt = update(user_settings_table).where(user_settings_table.c.user_id == uid).values(**update_data)
        await db.execute(upd_stmt)
        await db.commit()
        
        # Fetch updated settings
        stmt = select(user_settings_table).where(user_settings_table.c.user_id == uid)
        result = await db.execute(stmt)
        settings_row = result.first()
        settings_dict = settings_row._asdict() if settings_row else {}
        if settings_dict.get('categories') is None:
            settings_dict['categories'] = []
        return UserSettingsBase(**settings_dict)

async def update_user_subscription_in_db(uid: str, sub_update: SubscriptionUpdate) -> bool:
    async with AsyncSessionLocal() as db:
        # Avoid timezone offset issues
        expires_at = sub_update.expires_at.replace(tzinfo=None) if sub_update.expires_at else None
        
        upd_stmt = update(users_table).where(users_table.c.id == uid).values(
            subscription_active=sub_update.is_active,
            subscription_expires_at=expires_at
        )
        result = await db.execute(upd_stmt)
        await db.commit()
        return result.rowcount > 0
