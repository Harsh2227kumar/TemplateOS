"""
Remove generated DOCX/PDF files from storage when their rows go away (V1.6).

generated_files rows disappear when a document is deleted (ORM cascade) or,
through ON DELETE CASCADE in the database, when its template or owner is
deleted. Mapper `before_delete` hooks collect the affected stored paths into
`session.info`; they are deleted from storage only AFTER the transaction
commits (a rollback discards the list), so a failed delete never loses files
that rows still point at.

register() is called once from app/models/__init__.py.
"""

import logging

from sqlalchemy import event, select
from sqlalchemy.orm import Session, object_session

from app.services.storage_service import StorageError, storage_service

logger = logging.getLogger(__name__)

_PENDING_KEY = "generated_files_to_delete"


def delete_stored_files(paths) -> None:
    """Best-effort removal of stored files (missing files are ignored)."""
    for path in paths:
        if not path:
            continue
        try:
            storage_service.delete_file(path)
        except StorageError as exc:
            logger.warning("Could not remove generated file %s: %s", path, exc)


def _queue(target, paths) -> None:
    session = object_session(target)
    if session is None:
        return
    pending = session.info.setdefault(_PENDING_KEY, set())
    pending.update(path for path in paths if path)


def _paths_for(connection, where_clause) -> list[str]:
    from app.models.document import Document
    from app.models.generated_file import GeneratedFile

    rows = connection.execute(
        select(GeneratedFile.docx_path, GeneratedFile.pdf_path)
        .join(Document, Document.id == GeneratedFile.document_id)
        .where(where_clause)
    ).all()
    return [path for row in rows for path in row if path]


def _on_generated_file_delete(_mapper, _connection, target) -> None:
    _queue(target, (target.docx_path, target.pdf_path))


def _on_template_delete(_mapper, connection, target) -> None:
    from app.models.document import Document

    _queue(target, _paths_for(connection, Document.template_id == target.id))


def _on_user_delete(_mapper, connection, target) -> None:
    from app.models.document import Document

    _queue(target, _paths_for(connection, Document.created_by == target.id))


def _after_commit(session: Session) -> None:
    pending = session.info.pop(_PENDING_KEY, None)
    if pending:
        delete_stored_files(sorted(pending))


def _after_rollback(session: Session, _previous_transaction=None) -> None:
    session.info.pop(_PENDING_KEY, None)


def register() -> None:
    from app.models.generated_file import GeneratedFile
    from app.models.template import Template
    from app.models.user import User

    if event.contains(GeneratedFile, "before_delete", _on_generated_file_delete):
        return
    event.listen(GeneratedFile, "before_delete", _on_generated_file_delete)
    event.listen(Template, "before_delete", _on_template_delete)
    event.listen(User, "before_delete", _on_user_delete)
    event.listen(Session, "after_commit", _after_commit)
    event.listen(Session, "after_soft_rollback", _after_rollback)
