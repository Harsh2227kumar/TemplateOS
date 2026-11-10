"""
Document model for V1.4 Phase 2 — persists form values as drafts.

A document represents a user's working draft based on a template.
It stores the template reference, creator, optional name, status,
and has a one-to-many relationship with DocumentValue for field values.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, and_, select, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.clock import utc_now_naive
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.template import Template
    from app.models.user import User
    from app.models.document_value import DocumentValue
    from app.models.generated_file import GeneratedFile
    from app.models.document_version import DocumentVersion

DOCUMENT_STATUSES = ("draft", "generated", "submitted", "approved", "rejected", "final")


class Document(Base):
    __tablename__ = "documents"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "status" not in kwargs:
            self.status = "draft"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        default="draft",
        server_default=text("'draft'"),
        nullable=False,
        index=True,
    )
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

    # Relationships
    template: Mapped["Template"] = relationship("Template", back_populates="documents")
    creator: Mapped["User"] = relationship("User", back_populates="documents")
    values: Mapped[list["DocumentValue"]] = relationship(
        "DocumentValue", back_populates="document", cascade="all, delete-orphan"
    )
    # V1.7 P2: every Generate is a version (newest first). The DB FKs are ON
    # DELETE CASCADE as well.
    versions: Mapped[list["DocumentVersion"]] = relationship(
        "DocumentVersion",
        back_populates="document",
        order_by="DocumentVersion.version.desc()",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # One row per version. Not passive: the rows are deleted through the ORM
    # so app.services.generated_file_cleanup removes their stored files.
    generated_files: Mapped[list["GeneratedFile"]] = relationship(
        "GeneratedFile",
        back_populates="document",
        cascade="all, delete-orphan",
    )
    # The generated output of the highest version (read-only), None until
    # the first Generate. Keeps V1.6 code reading document.generated_file.
    generated_file: Mapped["GeneratedFile | None"] = relationship(
        "GeneratedFile",
        primaryjoin=lambda: _latest_generated_file_join(),
        viewonly=True,
        uselist=False,
    )

    @validates("status")
    def validate_status(self, _key: str, value: str) -> str:
        if value not in DOCUMENT_STATUSES:
            raise ValueError(f"Invalid status: {value}")
        return value


def _latest_generated_file_join():
    from app.models.document_version import DocumentVersion
    from app.models.generated_file import GeneratedFile

    latest_version_id = (
        select(DocumentVersion.id)
        .where(DocumentVersion.document_id == Document.id)
        .order_by(DocumentVersion.version.desc())
        .limit(1)
        .scalar_subquery()
    )
    return and_(
        GeneratedFile.document_id == Document.id,
        GeneratedFile.version_id == latest_version_id,
    )
