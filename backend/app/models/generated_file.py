"""
GeneratedFile model for V1.6 — the latest generated output of a document.

One row per document (1:1, document_id is UNIQUE). Regenerating replaces the
row's paths (upsert) and the superseded files are removed from storage.
Paths are relative to the storage root (generated/docx, generated/pdf);
binary content never lives in the database.

PDF state is derived from two columns:
- pdf_path set              -> "ok"
- pdf_path NULL, pdf_error  -> "failed" (conversion attempted and failed)
- both NULL                 -> "not_configured" (no converter available)

template_version / template_source_path snapshot which template file the
document was rendered from, so a later re-clean of the template can be told
apart from the generated output.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utc_now_naive
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document

PdfStatus = Literal["ok", "failed", "not_configured"]
PDF_ERROR_MAX_LENGTH = 500


class GeneratedFile(Base):
    __tablename__ = "generated_files"
    __table_args__ = (
        UniqueConstraint("document_id", name="uq_generated_files_document_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    docx_path: Mapped[str] = mapped_column(String(500), nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_error: Mapped[str | None] = mapped_column(
        String(PDF_ERROR_MAX_LENGTH), nullable=True
    )
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    template_source_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now_naive,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    document: Mapped["Document"] = relationship(
        "Document", back_populates="generated_file"
    )

    @property
    def pdf_status(self) -> PdfStatus:
        if self.pdf_path:
            return "ok"
        if self.pdf_error:
            return "failed"
        return "not_configured"
