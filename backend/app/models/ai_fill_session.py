"""
AiFillSession model (V1.7 Phase 2.2) - the AI fill chat of one document.

One chat per document (UNIQUE document_id). The chat is the user's own
document data, like document_values: it is deleted with the document
(CASCADE) and is never copied into ai_generations, audit_logs or the logs.

status: active -> completed (the chat reached the "ready" stage once; the
user can still send more messages).
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.clock import utc_now_naive
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.ai_fill_message import AiFillMessage

FILL_SESSION_STATUSES: tuple[str, ...] = ("active", "completed")


class AiFillSession(Base):
    __tablename__ = "ai_fill_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'completed')", name="ck_ai_fill_sessions_status"),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "status" not in kwargs:
            self.status = "active"
        if "turn_count" not in kwargs:
            self.turn_count = 0
        if "filled_count" not in kwargs:
            self.filled_count = 0

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Distinct fields proposed with high / medium confidence so far.
    filled_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now_naive, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now_naive,
        onupdate=utc_now_naive,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    # A user message and its assistant reply share the turn; "user" sorts
    # after "assistant", so the role order is descending.
    messages: Mapped[list["AiFillMessage"]] = relationship(
        "AiFillMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="(AiFillMessage.turn, AiFillMessage.role.desc())",
    )

    @validates("status")
    def validate_status(self, _key: str, value: str) -> str:
        if value not in FILL_SESSION_STATUSES:
            raise ValueError(f"Invalid AI fill session status: {value}")
        return value
