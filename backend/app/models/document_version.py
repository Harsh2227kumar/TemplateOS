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
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utc_now_naive
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.generated_file import GeneratedFile
    from app.models.user import User


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_document_versions_document_version"),
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

    document: Mapped["Document"] = relationship("Document", back_populates="versions")
    creator: Mapped["User | None"] = relationship("User")
    generated_file: Mapped["GeneratedFile | None"] = relationship(
        "GeneratedFile",
        back_populates="version",
        uselist=False,
        cascade="all, delete-orphan",
    )
