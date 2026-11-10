"""
CRUD helpers for editor_sessions (V1.7 Phase 2.1 - Member 3).

- open_or_reuse_session  -> one active (open / saving) session per target:
                            the same user gets their session back, another
                            user gets EditorLocked; stale sessions expire
- get_session_by_key     -> Document Server file / callback routes and polling
- mark_saving / mark_saved / mark_closed / mark_failed -> status changes

Locking is a database query (works across processes); nothing is held in
memory. None of the helpers commit.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.core.clock import utc_now_naive
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.editor_session import (
    ACTIVE_STATUSES,
    EDITOR_ERROR_MAX_LENGTH,
    EditorSession,
)
from app.models.template import Template
from app.models.user import User


@dataclass
class EditorLocked(Exception):
    """Another user is editing this file."""

    user_name: str
    since: datetime

    def __str__(self) -> str:
        return f"Being edited by {self.user_name} since {self.since:%H:%M}"


def new_session_key() -> str:
    """Random, url-safe and unique per session (the ONLYOFFICE document.key)."""
    return secrets.token_urlsafe(24)


def _target_filter(target_type: str, template_id: int | None, document_id: int | None):
    if target_type == "template":
        return (EditorSession.target_type == "template", EditorSession.template_id == template_id)
    return (EditorSession.target_type == "document", EditorSession.document_id == document_id)


def expire_stale_sessions(
    db: Session, target_type: str, template_id: int | None = None, document_id: int | None = None
) -> int:
    """Mark active sessions of a target past expires_at as expired."""
    now = utc_now_naive()
    result = db.execute(
        update(EditorSession)
        .where(
            *_target_filter(target_type, template_id, document_id),
            EditorSession.status.in_(ACTIVE_STATUSES),
            EditorSession.expires_at <= now,
        )
        .values(status="expired", updated_at=now)
        .execution_options(synchronize_session="fetch")
    )
    return result.rowcount or 0


def active_session(
    db: Session, target_type: str, template_id: int | None = None, document_id: int | None = None
) -> EditorSession | None:
    """The target's open / saving session that has not expired, if any."""
    return db.execute(
        select(EditorSession)
        .where(
            *_target_filter(target_type, template_id, document_id),
            EditorSession.status.in_(ACTIVE_STATUSES),
            EditorSession.expires_at > utc_now_naive(),
        )
        .order_by(EditorSession.created_at.desc())
        .options(selectinload(EditorSession.user))
        .limit(1)
    ).scalar_one_or_none()


def open_or_reuse_session(
    db: Session,
    *,
    user: User,
    target_type: str,
    source_path: str,
    ttl_minutes: int,
    template: Template | None = None,
    document: Document | None = None,
    base_version: DocumentVersion | None = None,
) -> tuple[EditorSession, bool]:
    """
    (session, reused). Raises EditorLocked when another user's session is
    active on the same target. Flushed, not committed.
    """
    template_id = template.id if template is not None else None
    document_id = document.id if document is not None else None
    expire_stale_sessions(db, target_type, template_id, document_id)
    current = active_session(db, target_type, template_id, document_id)
    if current is not None:
        same_file = current.base_version_id == (base_version.id if base_version else None)
        if current.user_id == user.id and same_file:
            return current, True
        if current.user_id != user.id:
            owner = current.user
            raise EditorLocked(
                user_name=(owner.full_name or owner.email) if owner else "another user",
                since=current.created_at,
            )
        # Same user, another version of the document: close the old session.
        current.status = "closed"
    now = utc_now_naive()
    session = EditorSession(
        session_key=new_session_key(),
        target_type=target_type,
        template_id=template_id,
        document_id=document_id,
        base_version_id=base_version.id if base_version is not None else None,
        source_path=source_path,
        user_id=user.id,
        status="open",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=ttl_minutes),
    )
    db.add(session)
    db.flush()
    return session, False


def get_session_by_key(db: Session, session_key: str) -> EditorSession | None:
    if not session_key or len(session_key) > 64:
        return None
    return db.execute(
        select(EditorSession)
        .where(EditorSession.session_key == session_key)
        .options(selectinload(EditorSession.user))
    ).scalar_one_or_none()


def latest_session_for_target(
    db: Session, target_type: str, template_id: int | None = None, document_id: int | None = None
) -> EditorSession | None:
    return db.execute(
        select(EditorSession)
        .where(*_target_filter(target_type, template_id, document_id))
        .order_by(EditorSession.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _set(session: EditorSession, status: str) -> EditorSession:
    session.status = status
    session.updated_at = utc_now_naive()
    return session


def mark_saving(session: EditorSession) -> EditorSession:
    return _set(session, "saving")


def mark_saved(
    session: EditorSession, *, result_revision: int | None = None, result_version: int | None = None
) -> EditorSession:
    session.result_revision = result_revision
    session.result_version = result_version
    session.error = None
    return _set(session, "saved")


def mark_closed(session: EditorSession) -> EditorSession:
    return _set(session, "closed")


def mark_failed(session: EditorSession, error: str) -> EditorSession:
    message = (error or "The file could not be saved").strip()
    if len(message) > EDITOR_ERROR_MAX_LENGTH:
        message = message[: EDITOR_ERROR_MAX_LENGTH - 3] + "..."
    session.error = message
    return _set(session, "failed")
