"""
Opaque refresh tokens for cookie sessions (see app/crud/refresh_token_crud.py).

Only the SHA-256 hash of a token is stored, so a database leak does not hand
out live sessions. Every login starts a new `family_id`; each rotation issues
a new row in the same family and revokes the old one (`replaced_by_id` points
at its successor). Presenting a revoked token is treated as theft and revokes
the whole family.

Timestamps are naive UTC, like the rest of the schema.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64))
    family_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    replaced_by_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
