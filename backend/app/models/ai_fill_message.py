"""
AiFillMessage model (V1.7 Phase 2.2) - one message of an AI fill chat.

A turn is a user row plus the assistant's reply (same `turn`). JSON is stored
as Text and parsed only in app.crud.ai_fill_crud:

- user rows:      answers = {"answers": [{question_id, choice}], "skipped": [question_id]}
- assistant rows: proposals = [{field_name, value, items, source_text,
                  confidence, reason, over_budget}], questions = [{id, text,
                  field_names, choices, kind, attempt}], stage, model
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.clock import utc_now_naive
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.ai_fill_session import AiFillSession

FILL_ROLES: tuple[str, ...] = ("user", "assistant")
FILL_STAGES: tuple[str, ...] = ("asking", "filling", "ready")


class AiFillMessage(Base):
    __tablename__ = "ai_fill_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "turn", "role", name="uq_ai_fill_messages_turn_role"),
        CheckConstraint("role IN ('user', 'assistant')", name="ck_ai_fill_messages_role"),
        CheckConstraint(
            "stage IS NULL OR stage IN ('asking', 'filling', 'ready')",
            name="ck_ai_fill_messages_stage",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_fill_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    turn: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    answers: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposals: Mapped[str | None] = mapped_column(Text, nullable=True)
    questions: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage: Mapped[str | None] = mapped_column(String(10), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now_naive, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    session: Mapped["AiFillSession"] = relationship("AiFillSession", back_populates="messages")

    @validates("role")
    def validate_role(self, _key: str, value: str) -> str:
        if value not in FILL_ROLES:
            raise ValueError(f"Invalid AI fill message role: {value}")
        return value

    @validates("stage")
    def validate_stage(self, _key: str, value: str | None) -> str | None:
        if value is not None and value not in FILL_STAGES:
            raise ValueError(f"Invalid AI fill stage: {value}")
        return value
