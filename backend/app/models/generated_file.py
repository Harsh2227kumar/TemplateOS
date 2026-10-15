"""
GeneratedFile model for V1.6 — the latest generated output of a document.

One row per document (1:1, document_id is UNIQUE). Regenerating replaces the
row's paths (upsert) and the superseded files are removed from storage.
Paths are relative to the storage root (generated/docx, generated/pdf);
binary content never lives in the database.

PDF conversion state (V1.6 Phase 2) is stored, not derived:
- pdf_status        pending (DOCX saved, conversion not finished yet)
                    | converted | failed
- pdf_error         short user-readable reason of the last failure
- pdf_converted_at  when the current PDF was produced
- pdf_attempts      conversions tried for the current DOCX (initial + retries)
A failed retry keeps an earlier PDF (pdf_path) of the same DOCX, so
pdf_status can be "failed" while a PDF is still downloadable.

template_version / template_source_path snapshot which template file the
document was rendered from, so a later re-clean of the template can be told
apart from the generated output.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Literal, get_args

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.clock import utc_now_naive
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document

PdfStatus = Literal["pending", "converted", "failed"]
PDF_STATUSES: tuple[str, ...] = get_args(PdfStatus)
PDF_ERROR_MAX_LENGTH = 500


class GeneratedFile(Base):
    __tablename__ = "generated_files"
    __table_args__ = (
        UniqueConstraint("document_id", name="uq_generated_files_document_id"),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "pdf_status" not in kwargs:
            self.pdf_status = "pending"
        if "pdf_attempts" not in kwargs:
            self.pdf_attempts = 0

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
    pdf_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    pdf_converted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pdf_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
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

    @validates("pdf_status")
    def validate_pdf_status(self, _key: str, value: str) -> str:
        if value not in PDF_STATUSES:
            raise ValueError(f"Invalid pdf_status: {value}")
        return value

    @property
    def has_pdf(self) -> bool:
        return self.pdf_path is not None
