"""
EkLink sync bookkeeping (SYNC_CONTRACT.md section 6): a single row (id 1).

- last_event_id: the highest EkLink change event applied; events with an id
  at or below it are skipped (pushes and pulls may overlap).
- last_pull_at / last_push_at / last_full_sync_at: when each path last ran.
- last_error (+ last_error_at): the last failure (cleared by a success).
- last_result: counts of the last batch ({"applied": n, "skipped": n, ...}).
- pending: event data whose codes did not resolve yet; retried after every
  batch and replaced by a full resync.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SyncState(Base):
    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    last_event_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), default=0, server_default="0", nullable=False
    )
    last_pull_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_push_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_full_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    pending: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
