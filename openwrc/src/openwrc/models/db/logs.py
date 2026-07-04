import enum
from datetime import datetime
from sqlalchemy import Index, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .event import EventMetadata


class EtlType(str, enum.Enum):
    """
    One value per atomic ETL function in WrcEtlService.
    Composite orchestrators (etl_historical_event, etl_event_timings, etc.)
    do not get their own type — completeness is derived by checking all atoms.
    """

    CATALOG = "catalog"
    EVENT_METADATA = "event_metadata"
    ITINERARY = "itinerary"
    ENTRIES = "entries"
    STAGE_RESULTS = "stage_results"
    STAGE_TIMES = "stage_times"
    SPLIT_TIMES = "split_times"


class EtlRunLog(Base):
    __tablename__ = "etl_run_log"

    __table_args__ = (
        # Covers the _latest_run lookup: filter on (etl_type, event_id, completed_at IS NOT NULL)
        # ordered by completed_at DESC. SQLite uses the index for equality + range scans.
        Index(
            "ix_etl_run_log_type_event_completed",
            "etl_type",
            "event_id",
            "completed_at",
        ),
    )

    # init=False fields first — excluded from __init__ so they don't affect ordering
    run_id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, init=False, default=None
    )

    # Required fields (no default) — must come before optional fields
    etl_type: Mapped[str] = mapped_column(String(50))
    started_at: Mapped[datetime]

    # Optional fields (have defaults) — must come after required fields
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey(EventMetadata.event_id), nullable=True, default=None
    )
    # None until the run completes successfully
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)
    # None means data never expires (historical events)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)
