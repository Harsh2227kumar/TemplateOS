"""
Word file editor workflows (V1.7 Phase 2.1) on top of ONLYOFFICE Docs.

Templates
- customize_template: a user's private copy of a template they may view
  ("Customize for me"); the original is never changed by them.
- open_template_session: edit the fill-ready DOCX (managers only: the
  uploader, scope admins, super_admin, or the owner of a personal copy).
- a saved template edit becomes revision N+1. A file docxtpl can parse
  becomes the template's fill-ready file; one it cannot parse is kept as a
  revision but NOT activated (the session reports the error).
- restore_revision: a copy of an older revision's file becomes current.

Generated documents
- open_document_session: edit one version's DOCX (editable documents only).
- a saved edit becomes version N+1 with source "manual_edit" (snapshot
  copied from the base, values unchanged), its own DOCX, a PDF converted
  with Gotenberg, and retention like any version.

Callbacks (handle_callback) come from the Document Server and are verified
with the shared JWT secret; storage failures roll back and remove the new
file, mark the session failed and answer {"error": 1}.
"""

import logging
from datetime import timezone
from pathlib import PurePosixPath

from fastapi import HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.clock import utc_now_naive
from app.core.config import settings
from app.crud.document_version_crud import (
    create_version,
    get_version,
    latest_version_number,
)
from app.crud.editor_session_crud import (
    EditorLocked,
    get_session_by_key,
    mark_closed,
    mark_failed,
    mark_saved,
    mark_saving,
    open_or_reuse_session,
)
from app.crud.generated_file_crud import create_generated_file
from app.crud.template_copy_crud import copy_template_for_user, stored_paths
from app.crud.template_revision_crud import (
    add_revision,
    field_changes,
    get_revision,
    list_revisions,
)
from app.models.document import Document
from app.models.editor_session import EditorSession
from app.models.template import Template
from app.models.user import User
from app.schemas.editor import (
    AddedPlaceholderRead,
    EditorConfigResponse,
    EditorSessionRead,
    EditorStatusConfig,
    FieldChangesRead,
    TemplateRevisionRead,
)
from app.services import onlyoffice_service
from app.services.document_generation import (
    convert_and_record,
    download_filename,
    prune_after_generate,
)
from app.services.document_permissions import document_permissions
from app.services.docx_cleaner import check_renderable, get_renderable_path
from app.services.generated_file_cleanup import delete_stored_files
from app.services.onlyoffice_service import (
    STATUS_CLOSED_NO_CHANGES,
    STATUS_EDITING,
    STATUS_FORCE_SAVE,
    STATUS_FORCE_SAVE_ERROR,
    STATUS_READY_FOR_SAVING,
    STATUS_SAVE_ERROR,
    CallbackRejected,
    EditedFileRejected,
)
from app.services.storage_service import StorageError, storage_service
from app.services.template_access import can_manage, user_can_view_template

logger = logging.getLogger(__name__)

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DELETED_USER = "Deleted user"
# Template statuses that mean "fields reviewed"; a field change sends them
# back to placeholder_detected so the UI asks for a review.
_REVIEWED_STATUSES = ("field_configured", "active")


# ── Availability and reads ────────────────────────────────────────


def editor_status() -> EditorStatusConfig:
    enabled = onlyoffice_service.editor_enabled()
    return EditorStatusConfig(
        enabled=enabled,
        document_server_url=settings.onlyoffice_public_base if enabled else None,
    )


def require_editor() -> None:
    if not onlyoffice_service.editor_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The document editor is not available on this server",
        )


def session_read(session: EditorSession) -> EditorSessionRead:
    return EditorSessionRead(
        session_key=session.session_key,
        status=session.status,
        target_type=session.target_type,
        template_id=session.template_id,
        document_id=session.document_id,
        result_revision=session.result_revision,
        result_version=session.result_version,
        error=session.error,
        created_at=session.created_at,
        updated_at=session.updated_at,
        expires_at=session.expires_at,
    )


def owned_session(db: Session, user: User, session_key: str) -> EditorSession:
    """The session for its owner; 404 for everyone else (keys are not guessable)."""
    session = get_session_by_key(db, session_key)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Editor session not found")
    if session.status in ("open", "saving") and session.expires_at <= utc_now_naive():
        session.status = "expired"
        db.commit()
    return session


def _config_response(session: EditorSession, *, title: str, user: User, reused: bool) -> EditorConfigResponse:
    return EditorConfigResponse(
        session_key=session.session_key,
        document_server_url=settings.onlyoffice_public_base or "",
        config=onlyoffice_service.build_config(session, title=title, user=user),
        reused=reused,
    )


def _locked(exc: EditorLocked) -> HTTPException:
    """
    409 with the holder and an ISO UTC `since`, so the browser can show the
    time in the user's zone ("detail" keeps a UTC fallback text).
    """
    since = exc.since if exc.since.tzinfo else exc.since.replace(tzinfo=timezone.utc)
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "detail": f"{exc} UTC",
            "code": "editor_locked",
            "user_name": exc.user_name,
            "since": since.isoformat(),
        },
    )


def _title(name: str | None, fallback: str) -> str:
    stem = (name or "").strip() or fallback
    return stem if stem.lower().endswith(".docx") else f"{stem}.docx"


# ── Templates ─────────────────────────────────────────────────────


def customize_template(db: Session, user: User, template: Template) -> Template:
    """A private copy of `template` for `user` (committed)."""
    if not user_can_view_template(user, template):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this template")
    if not get_renderable_path(template):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Template has no source file")
    copy = None
    try:
        copy = copy_template_for_user(db, template, user)
        db.commit()
    except StorageError:
        db.rollback()
        if copy is not None:
            delete_stored_files(stored_paths(copy))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The template file is missing on the server") from None
    except Exception:
        db.rollback()
        if copy is not None:
            delete_stored_files(stored_paths(copy))
        raise
    db.refresh(copy)
    logger.info("User %s customized template %s as %s", user.id, template.id, copy.id)
    return copy


def open_template_session(db: Session, user: User, template: Template) -> EditorConfigResponse:
    require_editor()
    if not can_manage(user, template):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit templates you manage. Use \"Customize for me\" to edit your own copy.",
        )
    source = get_renderable_path(template)
    if not source or not storage_service.exists(source):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The template file is missing on the server")
    try:
        session, reused = open_or_reuse_session(
            db,
            user=user,
            target_type="template",
            template=template,
            source_path=source,
            ttl_minutes=settings.editor_session_ttl_minutes,
        )
    except EditorLocked as exc:
        db.rollback()
        raise _locked(exc) from None
    db.commit()
    return _config_response(session, title=_title(template.name, f"template-{template.id}"), user=user, reused=reused)


def revision_reads(db: Session, template: Template) -> list[TemplateRevisionRead]:
    current = get_renderable_path(template)
    rows = list_revisions(db, template.id)
    current_revision = next((r.revision for r in rows if r.file_path == current), None)
    return [
        TemplateRevisionRead(
            revision=row.revision,
            source=row.source,
            created_at=row.created_at,
            created_by_name=(row.creator.full_name or row.creator.email) if row.creator else DELETED_USER,
            placeholders_added=row.added_names,
            placeholders_removed=row.removed_names,
            blank_suggestions=row.blank_suggestions,
            note=row.note,
            is_current=row.revision == current_revision,
        )
        for row in rows
    ]


def field_changes_read(db: Session, template: Template) -> FieldChangesRead:
    changes = field_changes(db, template)
    return FieldChangesRead(
        template_id=template.id,
        revision=changes.revision,
        added=[AddedPlaceholderRead(**vars(item)) for item in changes.added],
        removed=changes.removed,
        blank_suggestions=changes.blank_suggestions,
        renderable=changes.renderable,
        render_error=changes.render_error,
        has_changes=changes.has_changes,
    )


def _activate_template_file(
    db: Session, template: Template, *, path: str, content: bytes, source: str, user_id: int | None, note: str | None
):
    """
    Record revision N+1 for a stored file; switch the template to it when
    docxtpl can parse it. Returns (revision, render_error). Not committed.

    The file becomes both the fill-ready file and the cleaning source, so
    "Turn blanks into fields" works on the edited text (cleaning reads
    original_file_path); the uploaded original stays in revision 1.
    """
    error = check_renderable(content)
    template.version = (template.version or 1) + 1
    revision = add_revision(
        db,
        template,
        source=source,
        file_path=path,
        created_by=user_id,
        docx_bytes=content,
        note=f"Not activated: {error}" if error else note,
    )
    if error is None:
        template.processed_file_path = path
        template.original_file_path = path
        if (revision.added_names or revision.removed_names) and template.status in _REVIEWED_STATUSES:
            template.status = "placeholder_detected"
    return revision, error


def restore_revision(db: Session, user: User, template: Template, number: int) -> Template:
    if not can_manage(user, template):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to restore this template")
    revision = get_revision(db, template.id, number)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Revision {number} does not exist")
    try:
        content = storage_service.read_bytes(revision.file_path)
    except StorageError:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=f"The file of revision {number} is missing on the server") from None
    error = check_renderable(content)
    if error:
        raise HTTPException(status_code=422, detail=f"Revision {number} cannot be used: {error}")
    stored = storage_service.save_bytes("templates_revisions", template.original_filename or "template.docx", content)
    try:
        _activate_template_file(
            db, template, path=stored.path, content=content, source="restore",
            user_id=user.id, note=f"Restored revision {number}",
        )
        db.commit()
    except Exception:
        db.rollback()
        delete_stored_files([stored.path])
        raise
    db.refresh(template)
    return template


# ── Documents ─────────────────────────────────────────────────────


def open_document_session(
    db: Session, user: User, document: Document, version_number: int | None
) -> EditorConfigResponse:
    require_editor()
    permissions = document_permissions(user, document)
    if document.created_by != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own documents")
    if not permissions.can_edit:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This document can no longer be edited")
    number = version_number or latest_version_number(db, document.id)
    if number is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The document has not been generated yet")
    version = get_version(db, document.id, number)
    if version is None or version.generated_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Version {number} does not exist")
    record = version.generated_file
    if record.files_pruned or not storage_service.exists(record.docx_path):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"The files of version {number} were removed. Restore its values and generate again.",
        )
    try:
        session, reused = open_or_reuse_session(
            db,
            user=user,
            target_type="document",
            document=document,
            base_version=version,
            source_path=record.docx_path,
            ttl_minutes=settings.editor_session_ttl_minutes,
        )
    except EditorLocked as exc:
        db.rollback()
        raise _locked(exc) from None
    db.commit()
    stem = download_filename(document, "docx")[: -len(".docx")]
    return _config_response(session, title=f"{stem} v{number}.docx", user=user, reused=reused)


# ── Document Server routes ────────────────────────────────────────


def serve_session_file(db: Session, session_key: str, token: str | None) -> FileResponse:
    """The file an editor session opens (Document Server only, signed URL)."""
    session = get_session_by_key(db, session_key)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not onlyoffice_service.editor_enabled() or not onlyoffice_service.verify_file_token(session, token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired file link")
    if session.status not in ("open", "saving"):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This editor session has ended")
    try:
        path = storage_service.file_path(session.source_path)
    except StorageError:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="The file is missing on the server") from None
    return FileResponse(
        path,
        media_type=DOCX_MEDIA_TYPE,
        filename=PurePosixPath(session.source_path).name,
        headers={"Cache-Control": "no-store"},
    )


def _store_template_edit(db: Session, session: EditorSession, content: bytes) -> None:
    template = session.template
    stored = storage_service.save_bytes("templates_revisions", template.original_filename or "template.docx", content)
    try:
        revision, error = _activate_template_file(
            db, template, path=stored.path, content=content, source="manual_edit",
            user_id=session.user_id, note="Edited in the document editor",
        )
        if error:
            mark_failed(session, f"Saved as revision {revision.revision} but not used: the template could not be read ({error})")
            session.result_revision = revision.revision
        else:
            mark_saved(session, result_revision=revision.revision)
        db.commit()
    except Exception:
        db.rollback()
        delete_stored_files([stored.path])
        raise
    logger.info("Template %s: editor session %s saved revision %s", template.id, session.session_key, revision.revision)


def _store_document_edit(db: Session, session: EditorSession, content: bytes) -> None:
    document = session.document
    base = session.base_version
    session_id = session.id
    stem = download_filename(document, "docx")[: -len(".docx")]
    stored = storage_service.save_bytes("generated_docx", f"{stem}.docx", content)
    now = utc_now_naive()
    try:
        version = create_version(
            db,
            document,
            created_by=session.user_id,
            template_version=base.template_version if base is not None else None,
            source="manual_edit",
            base_version=base,
            created_at=now,
        )
        record = create_generated_file(
            db,
            version,
            docx_path=stored.path,
            generated_at=now,
            template_version=version.template_version,
            template_source_path=None,
        )
        session = db.get(EditorSession, session_id)  # create_version may have rolled back once
        mark_saved(session, result_version=version.version)
        db.commit()
    except Exception:
        db.rollback()
        delete_stored_files([stored.path])
        raise
    db.refresh(record)
    document_id = document.id
    try:
        convert_and_record(db, record, content, f"{stem}.docx")
    except Exception:  # the DOCX version is committed; the PDF stays "pending"
        logger.exception("Could not record the PDF of manually edited document %s", document_id)
        db.rollback()
    prune_after_generate(db, document_id)
    logger.info("Document %s: editor session saved manual version %s", document_id, version.version)


def handle_callback(db: Session, session_key: str, body: dict, authorization: str | None) -> dict:
    """Process an ONLYOFFICE callback; always answers {"error": 0 | 1}."""
    session = get_session_by_key(db, session_key)
    if session is None or not onlyoffice_service.editor_enabled():
        return {"error": 1}
    try:
        payload = onlyoffice_service.verify_callback(body, authorization)
    except CallbackRejected as exc:
        logger.warning("Rejected editor callback for session %s: %s", session_key, exc)
        return {"error": 1}
    if payload.get("key") not in (None, session.session_key):
        logger.warning("Editor callback key mismatch for session %s", session_key)
        return {"error": 1}

    callback_status = payload.get("status")
    if callback_status == STATUS_EDITING:
        return {"error": 0}
    if callback_status == STATUS_CLOSED_NO_CHANGES:
        if session.status in ("open", "saving"):
            mark_closed(session)
            db.commit()
        return {"error": 0}
    if callback_status in (STATUS_SAVE_ERROR, STATUS_FORCE_SAVE_ERROR):
        mark_failed(session, "The document editor could not save the file")
        db.commit()
        return {"error": 0}
    if callback_status not in (STATUS_READY_FOR_SAVING, STATUS_FORCE_SAVE):
        return {"error": 0}
    if session.status == "saved":
        return {"error": 0}  # repeated callback: already stored

    mark_saving(session)
    db.commit()
    session_id = session.id
    try:
        content = onlyoffice_service.download_edited_file(payload.get("url"))
        if session.target_type == "template":
            _store_template_edit(db, session, content)
        else:
            _store_document_edit(db, session, content)
    except EditedFileRejected as exc:
        db.rollback()
        session = db.get(EditorSession, session_id)
        mark_failed(session, str(exc))
        db.commit()
        return {"error": 1}
    except Exception:
        logger.exception("Storing the edited file of session %s failed", session_key)
        db.rollback()
        session = db.get(EditorSession, session_id)
        mark_failed(session, "The edited file could not be stored")
        db.commit()
        return {"error": 1}
    return {"error": 0}
