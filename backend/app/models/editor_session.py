"""
EditorSession model (V1.7 Phase 2.1) - one ONLYOFFICE editing session.

A session is created when a user opens a Word file in the editor (a
template's fill-ready DOCX or a generated document version). `session_key`
is the ONLYOFFICE `document.key`: random, unique and never reused, so the
Document Server never serves a cached older file. The Document Server
fetches the file and posts its save callback using this key; the result
of the save (template revision or document version) is recorded here so
the browser can poll for it.

Status flow: open -> saving -> saved | failed; open -> closed (no changes);
open/saving past expires_at -> expired. Only one open/saving session per
target at a time (locking is a database query, not memory).
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.clock import utc_now_naive
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.document_version import DocumentVersion
    from app.models.template import Template
    from app.models.user import User

TARGET_TYPES: tuple[str, ...] = ("template", "document")
SESSION_STATUSES: tuple[str, ...] = ("open", "saving", "saved", "closed", "failed", "expired")
ACTIVE_STATUSES: tuple[str, ...] = ("open", "saving")
EDITOR_ERROR_MAX_LENGTH = 500


class EditorSession(Base):
    __tablename__ = "editor_sessions"
    __table_args__ = (
        CheckConstraint("target_type IN ('template', 'document')", name="ck_editor_sessions_target_type"),
        CheckConstraint(
            "status IN ('open', 'saving', 'saved', 'closed', 'failed', 'expired')",
            name="ck_editor_sessions_status",
        ),
        CheckConstraint(
            "(target_type = 'template' AND template_id IS NOT NULL AND document_id IS NULL) OR "
            "(target_type = 'document' AND document_id IS NOT NULL AND template_id IS NULL)",
            name="ck_editor_sessions_target",
        ),
        Index("ix_editor_sessions_target", "target_type", "template_id", "document_id", "status"),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "status" not in kwargs:
            self.status = "open"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    target_type: Mapped[str] = mapped_column(String(10), nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("templates.id", ondelete="CASCADE"), nullable=True
    )
    document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True
    )
    base_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True
    )
    source_path: Mapped[str] = mapped_column(String(500), nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="open", server_default="open"
    )
    result_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(EDITOR_ERROR_MAX_LENGTH), nullable=True)
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
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped["User"] = relationship("User")
    template: Mapped["Template | None"] = relationship("Template")
    document: Mapped["Document | None"] = relationship("Document")
    base_version: Mapped["DocumentVersion | None"] = relationship("DocumentVersion")

    @validates("target_type")
    def validate_target_type(self, _key: str, value: str) -> str:
        if value not in TARGET_TYPES:
            raise ValueError(f"Invalid editor target: {value}")
        return value

    @validates("status")
    def validate_status(self, _key: str, value: str) -> str:
        if value not in SESSION_STATUSES:
            raise ValueError(f"Invalid editor session status: {value}")
        return value

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES and self.expires_at > utc_now_naive()
