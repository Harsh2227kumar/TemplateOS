"""
One successful DOCX/PDF download (V1.7 Phase 3).

History outlives its subjects: user / document / version are SET NULL on
delete, and document_name, version, version_source and file_name are
snapshots taken at download time, so a row stays readable after the
document (or the user) is gone.
"""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.base import Base

DOWNLOAD_FORMATS = ("docx", "pdf")


class DownloadHistory(Base):
    __tablename__ = "download_history"
    __table_args__ = (
        CheckConstraint("format IN ('docx', 'pdf')", name="ck_download_history_format"),
        Index("ix_download_history_user_downloaded", "user_id", "downloaded_at"),
        Index("ix_download_history_document_downloaded", "document_id", "downloaded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True
    )
    version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # generated | manual_edit (snapshot of document_versions.source, P2.1)
    version_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    format: Mapped[str] = mapped_column(String(4), nullable=False)
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    @validates("format")
    def validate_format(self, _key: str, value: str) -> str:
        if value not in DOWNLOAD_FORMATS:
            raise ValueError(f"Unsupported download format: {value}")
        return value

    @property
    def document_exists(self) -> bool:
        return self.document_id is not None
