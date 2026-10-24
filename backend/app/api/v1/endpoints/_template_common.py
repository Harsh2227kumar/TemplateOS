"""
Helpers shared by the template router modules (templates, template_placeholders,
template_cleaning, template_ai, template_fields). Internal: no routes here.
"""

import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud.template_crud import set_processed_path
from app.models.template import Template
from app.models.user import User
from app.services.storage_service import (
    StorageError,
    StoredFileNotFoundError,
    storage_service,
)
from app.services.template_access import can_manage

logger = logging.getLogger(__name__)


def require_manage(template: Template, user: User, action: str) -> None:
    """403 unless the user may manage (modify) this template."""
    if not can_manage(user, template):
        raise HTTPException(
            status_code=403,
            detail=f"You do not have permission to {action} this template",
        )


def read_stored(path: str) -> bytes:
    """Read a stored file; a file missing on disk is a 409."""
    try:
        return storage_service.read_bytes(path)
    except StoredFileNotFoundError:
        raise HTTPException(
            status_code=409, detail="Source file missing on disk"
        ) from None


def record_file_revision(
    db: Session, template: Template, path: str, content: bytes, source: str, user_id: int | None
) -> None:
    """
    V1.7 P2.1: the template's file changed -> version + 1 and a revision
    (clean / fix_placeholders / upload). Never fails the pipeline step.
    """
    from app.crud.template_revision_crud import add_revision

    try:
        if source != "upload":
            template.version = (template.version or 1) + 1
        add_revision(db, template, source=source, file_path=path, created_by=user_id, docx_bytes=content)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not record a %s revision for template %s", source, template.id)


def save_processed(db: Session, template: Template, processed_bytes: bytes) -> str:
    """
    Store a new processed copy. V1.7 P2.1: the superseded copy is kept, because
    template_revisions reference every stored template file (history and
    restore); stored files are removed when the template is deleted.
    """
    try:
        stored = storage_service.save_bytes(
            "templates_processed",
            template.original_filename or "template.docx",
            processed_bytes,
        )
    except StorageError as e:
        logger.error(f"Storage error while saving processed template {template.id}: {e}")
        raise HTTPException(
            status_code=500, detail="Could not save the cleaned template"
        ) from None
    set_processed_path(db, template, stored.path)
    return stored.path
