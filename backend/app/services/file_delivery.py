"""
Sending generated files (V1.7 Phase 3): the one place downloads are recorded.

Every download route checks permission and resolves the file itself (its
404 / 409 / 410 messages stay as they were), then calls deliver_file(),
which records a download_history row and a document.download audit event,
commits them, and returns the file. Failed downloads never get here, so
they are never recorded; HEAD requests are not recorded either.

The ONLYOFFICE Document Server fetching a file to open it
(GET /editor/files/{key}) is not a download and does not use this.
"""

import logging
from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.crud.download_history_crud import record_download
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.user import User
from app.services import audit_service, document_generation

logger = logging.getLogger(__name__)

MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


def _file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def deliver_file(
    db: Session,
    request: Request,
    *,
    user: User,
    document: Document,
    version: DocumentVersion | None,
    fmt: str,
    path: Path,
    filename: str,
) -> FileResponse:
    """Record the download (history + audit, committed), then stream `path` as `filename`."""
    if request.method != "HEAD":
        size = _file_size(path)
        try:
            with db.begin_nested():
                record_download(
                    db,
                    user=user,
                    document=document,
                    version=version,
                    fmt=fmt,
                    file_name=filename,
                    file_size=size,
                    ip=audit_service.client_ip(request),
                    user_agent=audit_service.user_agent(request),
                )
        except Exception:
            logger.exception("download history write failed for document %s", document.id)
        label = f" v{version.version}" if version is not None else ""
        audit_service.record(
            db,
            request,
            actor=user,
            action="document.download",
            entity_type="document",
            entity_id=document.id,
            summary=f"Downloaded {fmt.upper()} of '{document.name or f'Document {document.id}'}'{label}",
            details={
                "format": fmt,
                "version": version.version if version is not None else None,
                "version_source": version.source if version is not None else None,
                "file_size": size,
            },
            template=document.template,
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("download record commit failed for document %s", document.id)
    return FileResponse(
        path,
        media_type=MEDIA_TYPES[fmt],
        headers={
            "Content-Disposition": document_generation.content_disposition(filename),
            "Cache-Control": "no-store",
        },
    )
