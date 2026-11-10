"""
V1.7 Phase 2.1 - Word file editor schemas (ONLYOFFICE Docs).

- EditorStatusConfig      GET /system/editor-config (no secrets)
- EditorConfigResponse    POST .../editor-session: the signed editor config
                          the browser passes to DocsAPI.DocEditor unchanged
- EditorSessionRead       GET /editor/sessions/{key} (save status polling)
- TemplateRevisionRead    GET /templates/{id}/revisions
- FieldChangesRead        GET /templates/{id}/field-changes
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

EditorTarget = Literal["template", "document"]
EditorSessionStatus = Literal["open", "saving", "saved", "closed", "failed", "expired"]
RevisionSource = Literal["upload", "clean", "fix_placeholders", "customize", "manual_edit", "restore"]


class EditorStatusConfig(BaseModel):
    enabled: bool
    document_server_url: str | None = None


class EditorConfigResponse(BaseModel):
    session_key: str
    document_server_url: str
    # Opaque, signed ONLYOFFICE configuration (includes `token`).
    config: dict[str, Any]
    reused: bool = False


class EditorSessionRead(BaseModel):
    session_key: str
    status: EditorSessionStatus
    target_type: EditorTarget
    template_id: int | None = None
    document_id: int | None = None
    result_revision: int | None = None
    result_version: int | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class TemplateRevisionRead(BaseModel):
    revision: int
    source: RevisionSource
    created_at: datetime
    created_by_name: str
    placeholders_added: list[str]
    placeholders_removed: list[str]
    blank_suggestions: int
    note: str | None = None
    is_current: bool


class AddedPlaceholderRead(BaseModel):
    key: str
    suggested_label: str
    suggested_type: str


class FieldChangesRead(BaseModel):
    """What the current template file means for the form (see template_revision_crud.field_changes)."""

    template_id: int
    revision: int
    added: list[AddedPlaceholderRead]
    removed: list[str]
    blank_suggestions: int
    renderable: bool
    render_error: str | None = None
    has_changes: bool
