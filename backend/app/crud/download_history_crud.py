"""
Download history rows (V1.7 Phase 3).

record_download() snapshots the document name and version so the row stays
readable after the document is deleted. It does not commit: the download
route commits it together with its audit row.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.download_history import DownloadHistory
from app.models.user import User

USER_AGENT_MAX_LENGTH = 255


def _clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value[:limit]


def record_download(
    db: Session,
    *,
    user: User | None,
    document: Document,
    version: DocumentVersion | None,
    fmt: str,
    file_name: str,
    file_size: int | None,
    ip: str | None,
    user_agent: str | None,
) -> DownloadHistory:
    row = DownloadHistory(
        user_id=user.id if user is not None else None,
        document_id=document.id,
        version_id=version.id if version is not None else None,
        version=version.version if version is not None else None,
        version_source=version.source if version is not None else None,
        format=fmt,
        document_name=_clip((document.name or "").strip() or f"Document {document.id}", 255),
        file_name=_clip(file_name, 255),
        file_size=file_size,
        ip_address=_clip(ip, 45),
        user_agent=_clip(user_agent, USER_AGENT_MAX_LENGTH),
    )
    db.add(row)
    db.flush()
    return row


def _page(db: Session, conditions: list, page: int, limit: int) -> tuple[list[DownloadHistory], int]:
    total = db.scalar(select(func.count()).select_from(DownloadHistory).where(*conditions)) or 0
    rows = db.scalars(
        select(DownloadHistory)
        .where(*conditions)
        .order_by(DownloadHistory.downloaded_at.desc(), DownloadHistory.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return list(rows), total


def list_user_downloads(
    db: Session,
    user_id: int,
    *,
    page: int = 1,
    limit: int = 20,
    fmt: str | None = None,
    document_id: int | None = None,
) -> tuple[list[DownloadHistory], int]:
    """The user's own downloads, newest first, and how many there are."""
    conditions = [DownloadHistory.user_id == user_id]
    if fmt is not None:
        conditions.append(DownloadHistory.format == fmt)
    if document_id is not None:
        conditions.append(DownloadHistory.document_id == document_id)
    return _page(db, conditions, page, limit)


def list_document_downloads(
    db: Session, document_id: int, *, page: int = 1, limit: int = 20
) -> tuple[list[DownloadHistory], int]:
    """Every download of one document, newest first."""
    return _page(db, [DownloadHistory.document_id == document_id], page, limit)
