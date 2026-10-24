"""
Word file editor endpoints (V1.7 Phase 2.1, ONLYOFFICE Docs).

Browser (cookie auth):
- GET  /system/editor-config                      is the editor available
- POST /templates/{id}/customize                  personal copy ("Customize for me")
- POST /templates/{id}/editor-session             edit a template file (managers)
- GET  /templates/{id}/revisions                  file history
- POST /templates/{id}/revisions/{r}/restore      make an older revision current
- GET  /templates/{id}/field-changes              what the current file means for the form
- POST /documents/{id}/editor-session?version=n   edit a generated version's DOCX
- GET  /editor/sessions/{key}                     save status (session owner)

Document Server only (no cookies; signed):
- GET  /editor/files/{key}?token=...              the file to open
- POST /editor/callback/{key}                     save callbacks (JWT verified)
"""

from fastapi import APIRouter, Body, Header, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, DbSession
from app.api.v1.endpoints.templates import _template_response
from app.crud.document_crud import get_document_by_id
from app.crud.template_crud import get_template_by_id
from app.schemas.editor import (
    EditorConfigResponse,
    EditorSessionRead,
    EditorStatusConfig,
    FieldChangesRead,
    TemplateRevisionRead,
)
from app.schemas.template import TemplateResponse
from app.services import word_editor_service as editor
from app.services.template_access import can_manage, user_can_view_template

router = APIRouter()


def _template(db, template_id: int):
    template = get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return template


@router.get("/system/editor-config", response_model=EditorStatusConfig, tags=["system"])
def editor_config() -> EditorStatusConfig:
    """Whether the Word file editor is available, and where its script lives."""
    return editor.editor_status()


@router.post(
    "/templates/{template_id}/customize",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["templates"],
)
def customize_template(db: DbSession, current_user: CurrentUser, template_id: int) -> TemplateResponse:
    """Your own private copy of a template you can use (its fields included), to change freely."""
    copy = editor.customize_template(db, current_user, _template(db, template_id))
    return _template_response(copy, current_user)


@router.post(
    "/templates/{template_id}/editor-session",
    response_model=EditorConfigResponse,
    responses={403: {"description": "Not a manager"}, 409: {"description": "Being edited / no file"},
               503: {"description": "Editor disabled"}},
    tags=["templates"],
)
def open_template_editor(db: DbSession, current_user: CurrentUser, template_id: int) -> EditorConfigResponse:
    """Open the template's fill-ready Word file in the document editor."""
    return editor.open_template_session(db, current_user, _template(db, template_id))


@router.get("/templates/{template_id}/revisions", response_model=list[TemplateRevisionRead], tags=["templates"])
def template_revisions(db: DbSession, current_user: CurrentUser, template_id: int) -> list[TemplateRevisionRead]:
    template = _template(db, template_id)
    if not user_can_view_template(current_user, template):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this template")
    return editor.revision_reads(db, template)


@router.post(
    "/templates/{template_id}/revisions/{revision}/restore",
    response_model=TemplateResponse,
    tags=["templates"],
)
def restore_template_revision(
    db: DbSession, current_user: CurrentUser, template_id: int, revision: int
) -> TemplateResponse:
    template = editor.restore_revision(db, current_user, _template(db, template_id), revision)
    return _template_response(template, current_user)


@router.get("/templates/{template_id}/field-changes", response_model=FieldChangesRead, tags=["templates"])
def template_field_changes(db: DbSession, current_user: CurrentUser, template_id: int) -> FieldChangesRead:
    template = _template(db, template_id)
    if not can_manage(current_user, template):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to review this template")
    return editor.field_changes_read(db, template)


@router.post(
    "/documents/{document_id}/editor-session",
    response_model=EditorConfigResponse,
    responses={403: {"description": "Not the owner"}, 404: {"description": "No such version"},
               409: {"description": "Not editable / being edited"}, 410: {"description": "Files removed"},
               503: {"description": "Editor disabled"}},
    tags=["documents"],
)
def open_document_editor(
    db: DbSession,
    current_user: CurrentUser,
    document_id: int,
    version: int | None = Query(default=None, ge=1),
) -> EditorConfigResponse:
    """Open a generated version's Word file (default: the latest) in the document editor."""
    document = get_document_by_id(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return editor.open_document_session(db, current_user, document, version)


@router.get("/editor/sessions/{session_key}", response_model=EditorSessionRead, tags=["editor"])
def editor_session_status(db: DbSession, current_user: CurrentUser, session_key: str) -> EditorSessionRead:
    """Save status of your editor session (poll after closing the editor)."""
    return editor.session_read(editor.owned_session(db, current_user, session_key))


@router.get("/editor/files/{session_key}", response_class=FileResponse, include_in_schema=False)
def editor_file(db: DbSession, session_key: str, token: str | None = Query(default=None)) -> FileResponse:
    """The Document Server fetches the file to open (signed link, no cookies)."""
    return editor.serve_session_file(db, session_key, token)


@router.post("/editor/callback/{session_key}", include_in_schema=False)
def editor_callback(
    db: DbSession,
    session_key: str,
    body: dict = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
) -> dict:
    """ONLYOFFICE save callbacks (JWT verified). Always answers {"error": 0|1}."""
    return editor.handle_callback(db, session_key, body, authorization)
