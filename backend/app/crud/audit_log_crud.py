"""
Audit log rows (V1.7 Phase 3). Append-only: there is no update or delete
here (retention lives in scripts/prune_audit_logs.py).

add_audit_log() checks the action against the catalog, snapshots the
actor's email and caps details at 4 KB. It does not commit: the endpoint's
own commit includes the row.

search_audit_logs() / iter_audit_logs_for_export() scope in SQL through
audit_scope_filter(), so totals and pages only ever count visible rows.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.audit_catalog import ENTITY_TYPES, is_known_action
from app.services.audit_scope import audit_scope_filter

DETAILS_MAX_BYTES = 4096
SUMMARY_MAX_LENGTH = 500
EXPORT_MAX_ROWS = 10_000


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so they match literally (same rule as template_crud)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def encode_details(details: dict[str, Any] | None) -> str | None:
    """JSON text, or {"_truncated": true, "keys": [...]} when over 4 KB."""
    if not details:
        return None
    text = json.dumps(details, default=str, ensure_ascii=False, sort_keys=True)
    if len(text.encode("utf-8")) <= DETAILS_MAX_BYTES:
        return text
    return json.dumps({"_truncated": True, "keys": sorted(str(key) for key in details)[:50]})


def decode_details(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return {"_unreadable": True}
    return value if isinstance(value, dict) else {"value": value}


def add_audit_log(
    db: Session,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    summary: str,
    details: dict[str, Any] | None = None,
    organization_id: int | None = None,
    department_id: int | None = None,
    institute_id: int | None = None,
    ip: str | None = None,
    actor_email: str | None = None,
) -> AuditLog:
    if not is_known_action(action):
        raise ValueError(f"Unknown audit action: {action}")
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"Unknown audit entity type: {entity_type}")
    row = AuditLog(
        actor_id=actor.id if actor is not None else None,
        actor_email=(actor.email if actor is not None else actor_email or None),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        organization_id=organization_id,
        department_id=department_id,
        institute_id=institute_id,
        summary=(summary or action)[:SUMMARY_MAX_LENGTH],
        details=encode_details(details),
        ip_address=ip[:45] if ip else None,
    )
    db.add(row)
    db.flush()
    return row


@dataclass(frozen=True)
class AuditFilters:
    action: str | None = None
    actor_id: int | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    date_from: datetime | None = None
    # Exclusive upper bound (the caller turns an inclusive date into the next midnight).
    date_to: datetime | None = None
    q: str | None = None


def _conditions(viewer: User, filters: AuditFilters) -> list:
    conditions = []
    scope = audit_scope_filter(viewer)
    if scope is not None:
        conditions.append(scope)
    if filters.action:
        conditions.append(AuditLog.action == filters.action)
    if filters.actor_id is not None:
        conditions.append(AuditLog.actor_id == filters.actor_id)
    if filters.entity_type:
        conditions.append(AuditLog.entity_type == filters.entity_type)
    if filters.entity_id is not None:
        conditions.append(AuditLog.entity_id == filters.entity_id)
    if filters.date_from is not None:
        conditions.append(AuditLog.created_at >= filters.date_from)
    if filters.date_to is not None:
        conditions.append(AuditLog.created_at < filters.date_to)
    text = (filters.q or "").strip()
    if text:
        pattern = f"%{_escape_like(text.lower())}%"
        conditions.append(
            or_(
                func.lower(AuditLog.summary).like(pattern, escape="\\"),
                func.lower(func.coalesce(AuditLog.actor_email, "")).like(pattern, escape="\\"),
            )
        )
    return conditions


def search_audit_logs(
    db: Session, *, viewer: User, page: int = 1, limit: int = 50, filters: AuditFilters = AuditFilters()
) -> tuple[list[AuditLog], int]:
    """Rows `viewer` may read matching `filters`, newest first, and their total."""
    conditions = _conditions(viewer, filters)
    total = db.scalar(select(func.count()).select_from(AuditLog).where(*conditions)) or 0
    rows = db.scalars(
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return list(rows), total


def iter_audit_logs_for_export(
    db: Session, *, viewer: User, filters: AuditFilters = AuditFilters(), max_rows: int = EXPORT_MAX_ROWS
) -> Iterator[AuditLog]:
    """The same rows as search_audit_logs, newest first, at most `max_rows`, streamed."""
    statement = (
        select(AuditLog)
        .where(*_conditions(viewer, filters))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(max_rows)
        .execution_options(yield_per=500)
    )
    yield from db.scalars(statement)
