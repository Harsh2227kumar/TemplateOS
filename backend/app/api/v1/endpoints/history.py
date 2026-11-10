"""
Download history and audit log endpoints (V1.7 Phase 3).

- GET /me/downloads                      your own downloads (paginated)
- GET /documents/{id}/downloads          downloads of a document you own
- GET /admin/audit-logs                  audit rows in your admin scope
- GET /admin/audit-logs/actions          the action catalog (filter labels)
- GET /admin/audit-logs/export.csv       the same rows as CSV (max 10,000)

Audit scope (super_admin all, org_admin their organization,
department_admin their department, others 403) is applied in SQL by
app/crud/audit_log_crud.py.
"""

import csv
import io
from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.core.clock import utc_now_naive
from app.crud.audit_log_crud import AuditFilters, iter_audit_logs_for_export, search_audit_logs
from app.crud.document_crud import get_document_by_id
from app.crud.download_history_crud import list_document_downloads, list_user_downloads
from app.models.user import User
from app.schemas.audit import AuditActionOption, AuditLogItem, DownloadHistoryItem, Paginated
from app.services import audit_service
from app.services.audit_catalog import AUDIT_ACTIONS, ENTITY_TYPES, action_options
from app.services.audit_scope import can_view_audit
from app.services.document_permissions import require_document_viewer

router = APIRouter()

MAX_RANGE_DAYS = 366
CSV_COLUMNS = ("time_utc", "actor", "action", "entity_type", "entity_id", "summary", "ip_address")


# ── downloads ─────────────────────────────────────────────────────


@router.get("/me/downloads", response_model=Paginated[DownloadHistoryItem], tags=["history"])
def my_downloads(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    format: Literal["docx", "pdf"] | None = Query(None),
    document_id: int | None = Query(None, ge=1),
) -> Paginated[DownloadHistoryItem]:
    """Your own downloads, newest first (rows of deleted documents included)."""
    rows, total = list_user_downloads(
        db, current_user.id, page=page, limit=limit, fmt=format, document_id=document_id
    )
    return Paginated[DownloadHistoryItem](
        items=[DownloadHistoryItem.model_validate(row) for row in rows], total=total, page=page, limit=limit
    )


@router.get(
    "/documents/{document_id}/downloads",
    response_model=Paginated[DownloadHistoryItem],
    responses={403: {"description": "Not the owner"}, 404: {"description": "Document not found"}},
    tags=["history"],
)
def document_downloads(
    db: DbSession,
    current_user: CurrentUser,
    document_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> Paginated[DownloadHistoryItem]:
    """Every download of one of your documents, newest first."""
    document = get_document_by_id(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    require_document_viewer(current_user, document)
    rows, total = list_document_downloads(db, document_id, page=page, limit=limit)
    return Paginated[DownloadHistoryItem](
        items=[DownloadHistoryItem.model_validate(row) for row in rows], total=total, page=page, limit=limit
    )


# ── audit log ─────────────────────────────────────────────────────


def _require_audit_viewer(user: User) -> None:
    if not can_view_audit(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to the audit log")


def _filters(
    action: str | None,
    actor_id: int | None,
    entity_type: str | None,
    entity_id: int | None,
    date_from: date | None,
    date_to: date | None,
    q: str | None,
) -> AuditFilters:
    """Validated filters; `to` is inclusive (the whole day)."""
    if action and action not in AUDIT_ACTIONS:
        raise HTTPException(status_code=422, detail=f"Unknown action: {action}")
    if entity_type and entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown entity type: {entity_type}")
    if date_from and date_to:
        if date_from > date_to:
            raise HTTPException(status_code=422, detail="'from' must be on or before 'to'")
        if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
            raise HTTPException(status_code=422, detail=f"The date range can be at most {MAX_RANGE_DAYS} days")
    return AuditFilters(
        action=action or None,
        actor_id=actor_id,
        entity_type=entity_type or None,
        entity_id=entity_id,
        date_from=datetime.combine(date_from, time.min) if date_from else None,
        date_to=datetime.combine(date_to + timedelta(days=1), time.min) if date_to else None,
        q=(q or "").strip()[:200] or None,
    )


@router.get(
    "/admin/audit-logs",
    response_model=Paginated[AuditLogItem],
    responses={403: {"description": "Not an admin with an audit scope"}, 422: {"description": "Bad filters"}},
    tags=["admin"],
)
def audit_logs(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    action: str | None = Query(None),
    actor_id: int | None = Query(None, ge=1),
    entity_type: str | None = Query(None),
    entity_id: int | None = Query(None),
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    q: str | None = Query(None),
) -> Paginated[AuditLogItem]:
    """Audit rows you may read (your scope), newest first. Dates are UTC days; `to` is inclusive."""
    _require_audit_viewer(current_user)
    filters = _filters(action, actor_id, entity_type, entity_id, date_from, date_to, q)
    rows, total = search_audit_logs(db, viewer=current_user, page=page, limit=limit, filters=filters)
    return Paginated[AuditLogItem](
        items=[AuditLogItem.model_validate(row) for row in rows], total=total, page=page, limit=limit
    )


@router.get("/admin/audit-logs/actions", response_model=list[AuditActionOption], tags=["admin"])
def audit_actions(current_user: CurrentUser) -> list[AuditActionOption]:
    """The action catalog: [{action, label, area}] for the filter."""
    _require_audit_viewer(current_user)
    return [AuditActionOption(**option) for option in action_options()]


def _csv_cell(value: object) -> str:
    """Text for a CSV cell; formula-like values are prefixed so spreadsheets show them as text."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.get(
    "/admin/audit-logs/export.csv",
    response_class=StreamingResponse,
    responses={403: {"description": "Not an admin with an audit scope"}, 422: {"description": "Bad filters"}},
    tags=["admin"],
)
def export_audit_logs(
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    action: str | None = Query(None),
    actor_id: int | None = Query(None, ge=1),
    entity_type: str | None = Query(None),
    entity_id: int | None = Query(None),
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    q: str | None = Query(None),
) -> StreamingResponse:
    """The rows /admin/audit-logs would list (same scope and filters), newest first, max 10,000."""
    _require_audit_viewer(current_user)
    filters = _filters(action, actor_id, entity_type, entity_id, date_from, date_to, q)
    # Read now: the session is closed before a streamed body finishes.
    rows = [
        (
            row.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            row.actor_email or ("System" if row.actor_id is None else f"User {row.actor_id}"),
            row.action,
            row.entity_type,
            row.entity_id,
            row.summary,
            row.ip_address,
        )
        for row in iter_audit_logs_for_export(db, viewer=current_user, filters=filters)
    ]
    audit_service.record_and_commit(
        db,
        request,
        actor=current_user,
        action="admin.audit_export",
        entity_type="audit_log",
        summary=f"Exported {len(rows)} audit row(s)",
        details={
            "rows": len(rows),
            "filters": {
                key: value
                for key, value in {
                    "action": action, "actor_id": actor_id, "entity_type": entity_type, "entity_id": entity_id,
                    "from": date_from, "to": date_to, "q": q,
                }.items()
                if value not in (None, "")
            },
        },
    )

    def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        buffer.write("﻿")  # BOM: Excel opens UTF-8 correctly
        writer.writerow(CSV_COLUMNS)
        for row in rows:
            writer.writerow([_csv_cell(value) for value in row])
            if buffer.tell() > 64_000:
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate()
        yield buffer.getvalue()

    filename = f"audit-log-{utc_now_naive():%Y%m%d}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )
