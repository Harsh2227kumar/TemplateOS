"""
TemplateRevision model (V1.7 Phase 2.1) - one row per change of a template's file.

Every time the fill-ready DOCX of a template changes (upload, clean, fix
placeholders, personal copy, manual edit in ONLYOFFICE, restore) a revision
records a stored copy of that file, who made it and which placeholders
appeared or disappeared, so every change can be reviewed and reversed.
`revision` equals `templates.version` after the change.

Files are never overwritten: each revision points at its own stored copy
(removed from storage when the row is deleted, see generated_file_cleanup).
"""

import json
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
    from app.models.template import Template
    from app.models.user import User

REVISION_SOURCES: tuple[str, ...] = (
    "upload",
    "clean",
    "fix_placeholders",
    "customize",
    "manual_edit",
    "restore",
)


class TemplateRevision(Base):
    __tablename__ = "template_revisions"
    __table_args__ = (
        UniqueConstraint("template_id", "revision", name="uq_template_revisions_template_revision"),
        CheckConstraint(
            "source IN ('upload', 'clean', 'fix_placeholders', 'customize', 'manual_edit', 'restore')",
            name="ck_template_revisions_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now_naive, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    placeholders_added: Mapped[str | None] = mapped_column(Text, nullable=True)
    placeholders_removed: Mapped[str | None] = mapped_column(Text, nullable=True)
    blank_suggestions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    template: Mapped["Template"] = relationship("Template", back_populates="revisions")
    creator: Mapped["User | None"] = relationship("User")

    @validates("source")
    def validate_source(self, _key: str, value: str) -> str:
        if value not in REVISION_SOURCES:
            raise ValueError(f"Invalid revision source: {value}")
        return value

    @staticmethod
    def _names(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except ValueError:
            return []
        return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []

    @property
    def added_names(self) -> list[str]:
        return self._names(self.placeholders_added)

    @property
    def removed_names(self) -> list[str]:
        return self._names(self.placeholders_removed)
