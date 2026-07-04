"""
DB infrastructure: engine, session factory, schema init.
All other services take a WrcDatabase instance rather than managing their own engine.
"""

import logging
import os
import time
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import openwrc.models.db  # noqa: F401 — registers all model tables with Base.metadata
from openwrc.models.db.base import Base
from openwrc.models.db.views import create_views

_log = logging.getLogger("openwrc.db")
_DEBUG_SQL = os.getenv("WRC_DEBUG_SQL", "").lower() in ("1", "true")


def _attach_query_timing(engine) -> None:
    """Log SQL execution time at DEBUG level via SQLAlchemy cursor events."""

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("_query_start", []).append(time.perf_counter())

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        elapsed = time.perf_counter() - conn.info["_query_start"].pop()
        # Truncate long statements for readability
        preview = statement.replace("\n", " ").strip()[:120]
        _log.debug("%.3fs  %s", elapsed, preview)


class WrcDatabase:

    def __init__(self, db_path: str = "wrc.db") -> None:
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
        if _DEBUG_SQL:
            _attach_query_timing(self.engine)
        self._session_factory = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self._initialized = False

    async def _ensure_schema(self) -> None:
        if not self._initialized:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all, checkfirst=True)
                await conn.run_sync(create_views)
            self._initialized = True

    async def init(self) -> None:
        await self._ensure_schema()

    @asynccontextmanager
    async def session(self):
        await self._ensure_schema()
        async with self._session_factory() as s:
            yield s
