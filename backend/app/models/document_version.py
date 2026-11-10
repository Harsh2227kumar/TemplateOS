"""
DocumentVersion model (V1.7 Phase 2) - one row per Generate.

Every generation of a document creates version N+1: a self-contained JSON
snapshot of the values it was rendered from, plus (1:1) the generated_files
row holding that version's DOCX / PDF. A version stays viewable after the
template or its fields change, because the snapshot carries everything:

values_snapshot: JSON array sorted by field_name of
    {field_name, value, value_format, rich_content (dict | null),
     ai_modified, ai_action}

Rows and snapshots are kept forever; only the stored files of old versions
are pruned (generated_files.files_pruned_at, GENERATED_VERSIONS_KEEP_FILES).

V1.7 P2.1: `source` is "generated" (rendered from the values) or
"manual_edit" (the Word file of `base_version` edited by hand in
ONLYOFFICE; its snapshot is copied from the base, the values did not change).
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

VERSION_SOURCES: tuple[str, ...] = ("generated", "manual_edit")

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.generated_file import GeneratedFile
    from app.models.user import User


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_document_versions_document_version"),
        CheckConstraint("source IN ('generated', 'manual_edit')", name="ck_document_versions_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now_naive,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    values_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="generated", server_default="generated"
    )
    base_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True
    )

    document: Mapped["Document"] = relationship("Document", back_populates="versions")
    creator: Mapped["User | None"] = relationship("User")
    generated_file: Mapped["GeneratedFile | None"] = relationship(
        "GeneratedFile",
        back_populates="version",
        uselist=False,
        cascade="all, delete-orphan",
    )
    base_version: Mapped["DocumentVersion | None"] = relationship(
        "DocumentVersion", remote_side="DocumentVersion.id", foreign_keys=[base_version_id]
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "source" not in kwargs:
            self.source = "generated"

    @validates("source")
    def validate_source(self, _key: str, value: str) -> str:
        if value not in VERSION_SOURCES:
            raise ValueError(f"Invalid version source: {value}")
        return value
