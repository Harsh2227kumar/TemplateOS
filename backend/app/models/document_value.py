"""
DocumentValue model for V1.4 Phase 2 — stores user-entered values for each field in a document.

Each row represents a single field value for a document. Uses field_name (string)
as the key rather than field_id for resilience against template reconfiguration.
Values are stored as TEXT to accommodate textareas, JSON arrays for list fields,
and string representations of all primitive types.

V1.7 Phase 2:
- value_format "rich" (textarea fields only): rich_content holds the
  validated Tiptap JSON (app.services.rich_text) and `value` its plain-text
  projection, used by validation, AI, search and plain renders.
- ai_modified: the saved value is an AI result (ai_action) that the user did
  not edit afterwards; ai_modified_at is when it became true.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
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
    from app.models.document import Document

VALUE_FORMATS: tuple[str, ...] = ("plain", "rich")
# Same actions as POST /ai/improve-text (app.schemas.ai.AI_TEXT_ACTIONS).
AI_ACTIONS: tuple[str, ...] = ("grammar", "tone", "concise", "formal", "expand")


class DocumentValue(Base):
    __tablename__ = "document_values"

    __table_args__ = (
        UniqueConstraint("document_id", "field_name", name="uq_document_value_key"),
        CheckConstraint(
            "value_format IN ('plain', 'rich')", name="ck_document_values_value_format"
        ),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "value_format" not in kwargs:
            self.value_format = "plain"
        if "ai_modified" not in kwargs:
            self.ai_modified = False

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_format: Mapped[str] = mapped_column(
        String(10), nullable=False, default="plain", server_default="plain"
    )
    rich_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_modified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    ai_action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ai_modified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now_naive,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now_naive,
        onupdate=utc_now_naive,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    # Relationship
    document: Mapped["Document"] = relationship("Document", back_populates="values")

    @validates("value_format")
    def validate_value_format(self, _key: str, value: str) -> str:
        if value not in VALUE_FORMATS:
            raise ValueError(f"Invalid value_format: {value}")
        return value

    @validates("ai_action")
    def validate_ai_action(self, _key: str, value: str | None) -> str | None:
        if value is not None and value not in AI_ACTIONS:
            raise ValueError(f"Invalid ai_action: {value}")
        return value
