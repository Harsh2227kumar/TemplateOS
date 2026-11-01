"""
Writing audit rows from endpoints (V1.7 Phase 3).

record() adds one audit_logs row in a SAVEPOINT of the endpoint's session:
the endpoint's own commit includes it, and if writing it fails the error is
logged and only the savepoint is rolled back, so an audit problem never
breaks the user's action.

Never pass field values, file contents, passwords, tokens or cookies in
`details`: ids, names, counts and status changes only.
"""

import logging
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.audit_log_crud import add_audit_log
from app.models.template import Template
from app.models.user import User

logger = logging.getLogger(__name__)


def client_ip(request: Request | None) -> str | None:
    """The caller's IP; X-Forwarded-For only when the peer is a trusted proxy."""
    if request is None or request.client is None:
        return None
    peer = request.client.host
    if peer in settings.trusted_proxies:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:45]
    return peer[:45] if peer else None


def user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    return request.headers.get("user-agent") or None


def scope_for_template(template: Template | None, actor: User | None) -> tuple[int | None, int | None]:
    """(organization_id, department_id): the template's audience, else the actor's membership."""
    if template is not None and template.scope_organization_id is not None:
        return template.scope_organization_id, template.scope_department_id
    if actor is not None:
        return actor.organization_id, actor.department_id
    return None, None


def record(
    db: Session,
    request: Request | None,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    summary: str,
    details: dict[str, Any] | None = None,
    organization_id: int | None = None,
    department_id: int | None = None,
    template: Template | None = None,
    actor_email: str | None = None,
) -> None:
    """
    Add an audit row (not committed). Scope comes from `template` when given,
    else from the explicit ids, else from the actor's membership.
    """
    if template is not None:
        organization_id, department_id = scope_for_template(template, actor)
    elif organization_id is None and department_id is None and actor is not None:
        organization_id, department_id = actor.organization_id, actor.department_id
    try:
        with db.begin_nested():
            add_audit_log(
                db,
                actor=actor,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                summary=summary,
                details=details,
                organization_id=organization_id,
                department_id=department_id,
                ip=client_ip(request),
                actor_email=actor_email,
            )
    except Exception:
        logger.exception("audit write failed for %s (%s %s)", action, entity_type, entity_id)


def record_and_commit(db: Session, request: Request | None, **kwargs: Any) -> None:
    """record() for actions that already committed their own work."""
    record(db, request, **kwargs)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("audit commit failed for %s", kwargs.get("action"))
