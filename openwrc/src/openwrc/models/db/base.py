from datetime import datetime, timezone
from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass, Mapped, mapped_column


class Base(MappedAsDataclass, DeclarativeBase):
    """Base class for all database models with automatic timestamps"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        insert_default=lambda: datetime.now(timezone.utc),
        nullable=False,
        init=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        insert_default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
        init=False,
    )
