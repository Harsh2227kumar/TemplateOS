"""
EkLink change sync endpoints (rules: app/services/eklink_sync.py).

  POST /sync/eklink/events     EkLink -> TemplateOS push. Body: the compact
                               JWT (Content-Type: application/jwt) signed by
                               EkLink (ES256, JWKS, typ eklink-events+jwt,
                               aud = EKLINK_CLIENT_ID). No cookie / CSRF: the
                               signature is the authentication.
                               200 {"last_event_id": n}, 401 bad signature,
                               500 when applying failed (EkLink retries).

Admin (mounted under /admin):
  GET  /admin/sync/status      any admin
  POST /admin/sync/run         super_admin: pull changes now
  POST /admin/sync/full        super_admin: full snapshot resync
"""

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.models.user import User
from app.schemas.sync import SyncLinks, SyncPushResult, SyncRunResult, SyncStatus
from app.services import audit_service, eklink_sync, scopes

router = APIRouter()
admin_router = APIRouter()

MAX_BODY_BYTES = 2_000_000


def _token_from_body(raw: bytes, content_type: str) -> str:
    text = raw.decode("utf-8", errors="replace").strip()
    if "json" in content_type.lower():
        try:
            body = json.loads(text)
        except ValueError:
            body = None
        if isinstance(body, dict) and isinstance(body.get("token"), str):
            return body["token"].strip()
        if isinstance(body, str):
            return body.strip()
    return text


@router.post("/eklink/events", response_model=SyncPushResult)
async def receive_eklink_events(request: Request, db: DbSession) -> SyncPushResult:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Event batch too large")
    if not settings.eklink_sync_enabled_setting:
        raise HTTPException(status_code=503, detail="EkLink sync is switched off")
    token = _token_from_body(raw, request.headers.get("content-type", ""))
    if not token:
        raise HTTPException(status_code=401, detail="Missing EkLink event batch")
    try:
        outcome = await run_in_threadpool(eklink_sync.receive_push, db, token)
    except eklink_sync.SyncError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return SyncPushResult(last_event_id=outcome["last_event_id"])


# ── admin ────────────────────────────────────────────────────────────


def eklink_links() -> SyncLinks:
    base = settings.eklink_url
    if not base:
        return SyncLinks()
    return SyncLinks(
        admin=f"{base}/admin",
        users=f"{base}/admin/users",
        directory=f"{base}/admin/directory",
        approvers=f"{base}/admin/approvers",
    )


def build_status(db, user: User) -> SyncStatus:
    state = eklink_sync.get_state(db)
    db.commit()
    links = eklink_links()
    return SyncStatus(
        enabled=settings.eklink_sync_enabled,
        configured=settings.eklink_sync_configured,
        eklink_url=settings.eklink_url,
        eklink_admin_url=links.admin,
        links=links,
        interval_minutes=settings.eklink_sync_interval_minutes,
        full_at=settings.eklink_sync_full_at,
        can_run=user.role == "super_admin" and settings.eklink_sync_configured,
        last_event_id=int(state.last_event_id or 0),
        last_pull_at=state.last_pull_at,
        last_push_at=state.last_push_at,
        last_full_sync_at=state.last_full_sync_at,
        last_error=state.last_error,
        last_error_at=state.last_error_at,
        last_result=state.last_result,
        pending_count=len(state.pending or []),
    )


def _require_admin(user: User) -> None:
    if not scopes.is_admin(user):
        raise HTTPException(status_code=403, detail="Only administrators can view the EkLink sync")


def _require_super_admin(user: User) -> None:
    if user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Only a super admin can run the EkLink sync")
    if not settings.eklink_sync_configured:
        raise HTTPException(status_code=503, detail="EkLink sync is not configured")


@admin_router.get("/sync/status", response_model=SyncStatus)
def sync_status(current_user: CurrentUser, db: DbSession) -> SyncStatus:
    _require_admin(current_user)
    return build_status(db, current_user)


def _run(kind: str, current_user: User, db, request: Request) -> SyncRunResult:
    _require_super_admin(current_user)
    try:
        outcome = (
            eklink_sync.full_resync(db) if kind == "full" else eklink_sync.pull_changes(db)
        )
    except eklink_sync.SyncError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    audit_service.record_and_commit(
        db, request, actor=current_user,
        action="admin.eklink_full_resync" if kind == "full" else "admin.eklink_sync",
        entity_type="sync", entity_id=eklink_sync.STATE_ID,
        summary="Ran the EkLink full resync" if kind == "full" else "Pulled EkLink changes",
        details={"last_event_id": outcome["last_event_id"]},
        actor_scope=False,
    )
    return SyncRunResult(
        last_event_id=outcome["last_event_id"],
        result=outcome.get("result"),
        status=build_status(db, current_user),
    )


@admin_router.post("/sync/run", response_model=SyncRunResult)
def sync_run(current_user: CurrentUser, db: DbSession, request: Request) -> SyncRunResult:
    return _run("changes", current_user, db, request)


@admin_router.post("/sync/full", response_model=SyncRunResult)
def sync_full(current_user: CurrentUser, db: DbSession, request: Request) -> SyncRunResult:
    return _run("full", current_user, db, request)
