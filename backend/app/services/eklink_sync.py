"""
EkLink -> TemplateOS change sync (SYNC_CONTRACT.md sections 4 to 6).

EkLink owns people, placement, the directory and approver jobs; TemplateOS
keeps a mirror of them. Changes arrive two ways and go through one path:

- push:  POST /api/v1/sync/eklink/events with a JWT signed by EkLink
         (`verify_events_jwt`, then `apply_events`);
- pull:  GET {EKLINK_URL}/api/sync/changes?after=<last_event_id>
         (`pull_changes`) and the full snapshot (`full_resync`), from the
         background scheduler (app/services/eklink_scheduler.py) and the
         admin buttons.

Processing (`apply_events`): events in ascending id; ids at or below
sync_state.last_event_id are skipped; unknown types are skipped but still
advance last_event_id; every handler is an idempotent upsert by key.

Handlers:
- person.upserted        user by sub -> login_id -> email, with the sign-in
                         rules of app/services/eklink.py (`apply_role`,
                         `apply_identity`, placement by codes) plus is_active
                         and is_demo. Deactivation revokes the user's refresh
                         tokens (access tokens already fail: get_current_user
                         checks is_active).
- person.login_id_changed
- directory.upserted     organization / institute / department by codes;
                         created when missing (an uncoded row with the same
                         name is adopted), name / is_active / is_demo follow
                         EkLink. Nothing is ever deleted.
- approver.upserted      approver_assignments by eklink_id (source 'eklink');
                         an identical local row is adopted instead of being
                         duplicated. Person by sub -> login_id, scope by codes.

Data whose codes (or person) do not resolve yet is kept in
sync_state.pending and retried after every batch (never fails the batch);
a full resync replaces that list.

Nothing here prints or stores secrets; errors kept in sync_state.last_error
are short messages without credentials.
"""

from __future__ import annotations

import logging
import threading
from collections import Counter
from datetime import date
from typing import Any

import httpx
import jwt
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import utc_now_naive
from app.core.config import settings
from app.models.approver_assignment import APPROVER_TITLES, SCOPE_LEVELS, ApproverAssignment
from app.models.organization import Department, Institute, Organization
from app.models.refresh_token import RefreshToken
from app.models.sync_state import SyncState
from app.models.user import MEMBER_TYPES, User
from app.services import eklink, org_directory

logger = logging.getLogger(__name__)

EVENTS_JWT_TYPE = "eklink-events+jwt"
MAX_EVENTS_PER_PUSH = 500
PULL_PAGE_LIMIT = 500
MAX_PULL_PAGES = 50
PULL_TIMEOUT_SECONDS = 30
SNAPSHOT_TIMEOUT_SECONDS = 120
MAX_PENDING = 5000
STATE_ID = 1

KNOWN_TYPES = (
    "person.upserted",
    "person.login_id_changed",
    "directory.upserted",
    "approver.upserted",
)
DIRECTORY_LEVELS = ("organization", "institute", "department")

# One batch at a time per process (pushes, pulls and the scheduler overlap);
# on PostgreSQL the sync_state row is also locked for the batch.
_lock = threading.RLock()


class SyncError(Exception):
    """Sync failed; `detail` is safe to show an administrator."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


# ── state ────────────────────────────────────────────────────────────


def get_state(db: Session, *, lock: bool = False) -> SyncState:
    query = select(SyncState).where(SyncState.id == STATE_ID)
    if lock:
        query = query.with_for_update()
    state = db.scalar(query)
    if state is None:
        state = SyncState(id=STATE_ID, last_event_id=0, pending=[])
        db.add(state)
        db.flush()
    return state


def record_error(db: Session, message: str) -> None:
    """Store a failure (own transaction; never raises)."""
    try:
        db.rollback()
        state = get_state(db)
        state.last_error = message[:2000]
        state.last_error_at = utc_now_naive()
        db.commit()
    except Exception:  # pragma: no cover - the database itself is down
        logger.exception("Could not record the EkLink sync error")
        db.rollback()


# ── small helpers ────────────────────────────────────────────────────


def _str(data: dict, key: str, limit: int) -> str | None:
    value = data.get(key)
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def _code(data: dict, key: str) -> str | None:
    value = _str(data, key, 64)
    if value is None:
        return None
    code = "".join(value.split()).upper()
    return code[:32] or None


def _date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _bool(data: dict, key: str, default: bool) -> bool:
    value = data.get(key)
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _entity_key(kind: str, data: dict) -> str:
    if kind == "person.upserted":
        return f"person:{_str(data, 'sub', 64) or _str(data, 'login_id', 128) or _str(data, 'email', 255)}"
    if kind == "directory.upserted":
        return (
            f"directory:{data.get('level')}:{_code(data, 'org_code')}:"
            f"{_code(data, 'institute_code')}:{_code(data, 'code')}"
        )
    if kind == "approver.upserted":
        return f"approver:{_str(data, 'id', 64)}"
    return f"{kind}:{data!r}"[:200]


def revoke_sessions(db: Session, user_id: int) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utc_now_naive())
    )


# ── in-memory index (one query per table per batch) ──────────────────


class _Index:
    """Users, directory rows and approver rows of the database, keyed the way
    the handlers look them up. Kept current as handlers add / change rows,
    so a batch needs no per-event queries (the session does not autoflush)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.users_by_sub: dict[str, User] = {}
        self.users_by_login: dict[str, User] = {}
        self.users_by_email: dict[str, User] = {}
        for user in db.scalars(select(User)).all():
            self._index_user(user)
        self.orgs: dict[str, Organization] = {}
        self.org_names: dict[str, Organization] = {}
        for org in db.scalars(select(Organization)).all():
            self._index_org(org)
        self.insts: dict[tuple[int, str], Institute] = {}
        self.inst_names: dict[tuple[int, str], Institute] = {}
        for inst in db.scalars(select(Institute)).all():
            self._index_inst(inst)
        self.depts: dict[tuple[int, str], Department] = {}
        self.dept_names: dict[tuple[int, str], Department] = {}
        for dept in db.scalars(select(Department)).all():
            self._index_dept(dept)
        self.approvers: dict[str, ApproverAssignment] = {}
        self.local_approvers: list[ApproverAssignment] = []
        for row in db.scalars(select(ApproverAssignment)).all():
            if row.eklink_id:
                self.approvers[row.eklink_id] = row
            else:
                self.local_approvers.append(row)

    # users
    def _index_user(self, user: User) -> None:
        if user.eklink_sub:
            self.users_by_sub[user.eklink_sub] = user
        if user.login_id:
            self.users_by_login[user.login_id] = user
        if user.email:
            self.users_by_email[user.email.lower()] = user

    def reindex_user(self, user: User) -> None:
        for mapping in (self.users_by_sub, self.users_by_login, self.users_by_email):
            for key in [k for k, v in mapping.items() if v is user]:
                del mapping[key]
        self._index_user(user)

    def find_user(self, sub: str | None, login_id: str | None, email: str | None) -> User | None:
        if sub and sub in self.users_by_sub:
            return self.users_by_sub[sub]
        if login_id and login_id in self.users_by_login:
            return self.users_by_login[login_id]
        if email:
            return self.users_by_email.get(email.lower())
        return None

    def email_taken(self, value: str, user_id: int | None) -> bool:
        other = self.users_by_email.get(value.lower())
        return other is not None and (user_id is None or other.id != user_id)

    def login_id_taken(self, value: str, user_id: int | None) -> bool:
        other = self.users_by_login.get(value)
        return other is not None and (user_id is None or other.id != user_id)

    # directory
    def _index_org(self, org: Organization) -> None:
        if org.code:
            self.orgs[org.code.upper()] = org
        self.org_names[org.name.lower()] = org

    def _index_inst(self, inst: Institute) -> None:
        if inst.code:
            self.insts[(inst.organization_id, inst.code.upper())] = inst
        self.inst_names[(inst.organization_id, inst.name.lower())] = inst

    def _index_dept(self, dept: Department) -> None:
        if dept.institute_id is None:
            return
        if dept.code:
            self.depts[(dept.institute_id, dept.code.upper())] = dept
        self.dept_names[(dept.institute_id, dept.name.lower())] = dept

    def reindex_directory(self, row) -> None:
        if isinstance(row, Organization):
            maps, index = (self.orgs, self.org_names), self._index_org
        elif isinstance(row, Institute):
            maps, index = (self.insts, self.inst_names), self._index_inst
        else:
            maps, index = (self.depts, self.dept_names), self._index_dept
        for mapping in maps:
            for key in [k for k, v in mapping.items() if v is row]:
                del mapping[key]
        index(row)

    def placement(
        self, org_code: str | None, inst_code: str | None, dept_code: str | None
    ) -> tuple[Organization | None, Institute | None, Department | None, bool]:
        """(org, institute, department, resolved) for these codes."""
        org = self.orgs.get(org_code) if org_code else None
        if org_code and org is None:
            return None, None, None, False
        inst = self.insts.get((org.id, inst_code)) if (org and inst_code) else None
        if inst_code and inst is None:
            return org, None, None, False
        dept = self.depts.get((inst.id, dept_code)) if (inst and dept_code) else None
        if dept_code and dept is None:
            return org, inst, None, False
        return org, inst, dept, True


# ── handlers ─────────────────────────────────────────────────────────
# Each returns "applied" | "unresolved" | "skipped" | "conflict".


def _apply_person(db: Session, index: _Index, data: dict, counts: Counter) -> str:
    email = (_str(data, "email", 255) or "").lower() or None
    sub = _str(data, "sub", 64)
    login_id = _str(data, "login_id", 128)
    if not sub and not login_id and not email:
        return "skipped"
    role, member_type = eklink.map_role(data)
    if data.get("member_type") in MEMBER_TYPES:
        member_type = data["member_type"]
    is_active = _bool(data, "is_active", True)

    user = index.find_user(sub, login_id, email)
    if user is not None and user.eklink_sub and sub and user.eklink_sub != sub:
        logger.warning("EkLink sync: user %s is linked to another EkLink account", user.id)
        return "conflict"
    created = False
    if user is None:
        if role is None or not email or index.email_taken(email, None):
            return "skipped"
        user = User(email=email, full_name=email, role=role, hashed_password=None, is_active=True)
        db.add(user)
        created = True
    else:
        eklink.apply_role(user, role)
    eklink.apply_identity(
        db,
        user,
        data,
        email=email or (user.email or "").lower(),
        member_type=member_type,
        email_taken=index.email_taken,
        login_id_taken=index.login_id_taken,
    )
    if "is_demo" in data:
        user.is_demo = _bool(data, "is_demo", False)

    if user.is_active and not is_active:
        user.is_active = False
        if user.id is not None:
            revoke_sessions(db, user.id)
        counts["deactivated"] += 1
    elif not user.is_active and is_active:
        user.is_active = True
        counts["reactivated"] += 1

    # Placement: EkLink's codes, as deep as they go. No organization code
    # leaves the placement as it is (pure admins, incomplete EkLink rows).
    resolved = True
    org_code = _code(data, "org_code")
    if org_code:
        org, inst, dept, resolved = index.placement(
            org_code, _code(data, "institute_code"), _code(data, "department_code")
        )
        if resolved:
            org_directory.set_user_membership(user, org, dept, inst)
    if created:
        db.flush()
        counts["created"] += 1
    index.reindex_user(user)
    return "applied" if resolved else "unresolved"


def _apply_login_change(db: Session, index: _Index, data: dict, counts: Counter) -> str:
    sub = _str(data, "sub", 64)
    old = _str(data, "old_login_id", 128)
    new = _str(data, "new_login_id", 128)
    if not new:
        return "skipped"
    user = (index.users_by_sub.get(sub) if sub else None) or (
        index.users_by_login.get(old) if old else None
    )
    if user is None:
        return "skipped"  # a later person.upserted / full resync carries it
    if user.login_id == new:
        return "applied"
    if index.login_id_taken(new, user.id):
        return "conflict"
    user.login_id = new
    index.reindex_user(user)
    return "applied"


def _unique_name(name: str, code: str, taken) -> str:
    if not taken(name):
        return name
    return f"{name} ({code})"[:255]


def _set_directory_flags(row, data: dict) -> None:
    row.is_active = _bool(data, "is_active", True)
    if "is_demo" in data:
        row.is_demo = _bool(data, "is_demo", False)


def _rename(db: Session, index: _Index, row, name: str, counts: Counter) -> None:
    if row.name == name:
        return
    try:
        if isinstance(row, Organization):
            org_directory.rename_organization(db, row, name)
            column, attr = "organization_id", "organization"
        elif isinstance(row, Institute):
            org_directory.rename_institute(db, row, name)
            column, attr = None, None
        else:
            org_directory.rename_department(db, row, name)
            column, attr = "department_id", "department"
    except org_directory.DirectoryError:
        counts["name_conflicts"] += 1
        return
    if column:  # keep the in-session copies of the legacy name columns current
        for user in set(index.users_by_email.values()):
            if getattr(user, column) == row.id:
                setattr(user, attr, row.name)
    index.reindex_directory(row)


def _apply_directory(db: Session, index: _Index, data: dict, counts: Counter) -> str:
    level = data.get("level")
    code = _code(data, "code")
    name = org_directory.clean_name(_str(data, "name", 255)) or code
    if level not in DIRECTORY_LEVELS or not code:
        return "skipped"

    if level == "organization":
        row = index.orgs.get(code)
        if row is None:
            adopt = index.org_names.get(name.lower())
            if adopt is not None and adopt.code is None:
                row = adopt
                row.code = code
            else:
                row = Organization(
                    name=_unique_name(name, code, lambda n: n.lower() in index.org_names),
                    code=code,
                )
                db.add(row)
                db.flush()
                counts["created"] += 1
        _rename(db, index, row, name, counts)
        _set_directory_flags(row, data)
        index.reindex_directory(row)
        return "applied"

    org = index.orgs.get(_code(data, "org_code") or "")
    if org is None:
        return "unresolved"
    if level == "institute":
        inst_code = _code(data, "institute_code") or code
        row = index.insts.get((org.id, inst_code))
        if row is None:
            adopt = index.inst_names.get((org.id, name.lower()))
            if adopt is not None and adopt.code is None:
                row = adopt
                row.code = inst_code
            else:
                row = Institute(
                    organization_id=org.id,
                    name=_unique_name(name, inst_code, lambda n: (org.id, n.lower()) in index.inst_names),
                    code=inst_code,
                )
                db.add(row)
                db.flush()
                counts["created"] += 1
        _rename(db, index, row, name, counts)
        _set_directory_flags(row, data)
        index.reindex_directory(row)
        return "applied"

    inst = index.insts.get((org.id, _code(data, "institute_code") or ""))
    if inst is None:
        return "unresolved"
    row = index.depts.get((inst.id, code))
    if row is None:
        adopt = index.dept_names.get((inst.id, name.lower()))
        if adopt is not None and adopt.code is None:
            row = adopt
            row.code = code
        else:
            row = Department(
                organization_id=org.id,
                institute_id=inst.id,
                name=_unique_name(name, code, lambda n: (inst.id, n.lower()) in index.dept_names),
                code=code,
            )
            db.add(row)
            db.flush()
            counts["created"] += 1
    _rename(db, index, row, name, counts)
    _set_directory_flags(row, data)
    index.reindex_directory(row)
    return "applied"


def _apply_approver(db: Session, index: _Index, data: dict, counts: Counter) -> str:
    eklink_id = _str(data, "id", 36)
    title = _str(data, "title", 64)
    level = data.get("scope_level")
    if not eklink_id or title not in APPROVER_TITLES or level not in SCOPE_LEVELS:
        return "skipped"
    sub = _str(data, "person_sub", 64)
    login_id = _str(data, "login_id", 128)
    user = (index.users_by_sub.get(sub) if sub else None) or (
        index.users_by_login.get(login_id) if login_id else None
    )
    if user is None or user.id is None:
        return "unresolved"
    org, inst, dept, resolved = index.placement(
        _code(data, "org_code"),
        _code(data, "institute_code") if level != "organization" else None,
        _code(data, "department_code") if level == "department" else None,
    )
    if not resolved or org is None or (level != "organization" and inst is None) or (
        level == "department" and dept is None
    ):
        return "unresolved"
    scope_key = _str(data, "scope_key", 64)
    valid_from = _date(data.get("valid_from")) or utc_now_naive().date()
    valid_to = _date(data.get("valid_to"))
    inst_id = inst.id if inst else None
    dept_id = dept.id if dept else None

    row = index.approvers.get(eklink_id)
    if row is None:
        for local in index.local_approvers:
            if (
                local.user_id == user.id
                and local.title == title
                and local.scope_level == level
                and local.organization_id == org.id
                and local.institute_id == inst_id
                and local.department_id == dept_id
                and (local.scope_key or None) == scope_key
                and local.valid_to is None
            ):
                row = local
                index.local_approvers.remove(local)
                counts["adopted"] += 1
                break
    if row is None:
        row = ApproverAssignment(eklink_id=eklink_id, valid_from=valid_from)
        db.add(row)
        counts["created"] += 1
    row.eklink_id = eklink_id
    row.source = "eklink"
    row.user_id = user.id
    row.user = user
    row.title = title
    row.scope_level = level
    row.organization_id = org.id
    row.institute_id = inst_id
    row.department_id = dept_id
    row.scope_key = scope_key
    row.valid_from = valid_from
    row.valid_to = valid_to
    index.approvers[eklink_id] = row
    return "applied"


HANDLERS = {
    "person.upserted": _apply_person,
    "person.login_id_changed": _apply_login_change,
    "directory.upserted": _apply_directory,
    "approver.upserted": _apply_approver,
}
# Pending data is retried parents first.
RETRY_ORDER = {"directory.upserted": 0, "person.upserted": 1, "approver.upserted": 2}
LEVEL_ORDER = {level: n for n, level in enumerate(DIRECTORY_LEVELS)}


def _apply_one(db: Session, index: _Index, kind: str, data: Any, counts: Counter) -> str:
    handler = HANDLERS.get(kind)
    if handler is None or not isinstance(data, dict):
        return "skipped"
    return handler(db, index, data, counts)


def _retry_pending(
    db: Session, index: _Index, pending: list[dict], counts: Counter
) -> list[dict]:
    still: list[dict] = []
    ordered = sorted(
        pending,
        key=lambda item: (
            RETRY_ORDER.get(item.get("type"), 9),
            LEVEL_ORDER.get((item.get("data") or {}).get("level"), 0),
        ),
    )
    for item in ordered:
        outcome = _apply_one(db, index, item.get("type"), item.get("data"), counts)
        if outcome == "unresolved":
            still.append(item)
        elif outcome == "applied":
            counts["resolved_later"] += 1
    return still


def _merge_pending(pending: list[dict], kind: str, data: dict, outcome: str) -> list[dict]:
    """Newest data per entity wins; an applied event clears older pending data."""
    key = _entity_key(kind, data)
    kept = [item for item in pending if item.get("key") != key]
    if outcome == "unresolved":
        kept.append({"key": key, "type": kind, "data": data})
    return kept[-MAX_PENDING:]


# ── batches ──────────────────────────────────────────────────────────


def apply_events(db: Session, events: list[Any], *, source: str) -> dict:
    """
    Apply a batch of change events (push or pull) and commit. Returns
    {"last_event_id": n, "result": counts}. Raises on a database failure
    (nothing of the batch is kept; the error is recorded).
    """
    with _lock:
        try:
            state = get_state(db, lock=True)
            counts: Counter = Counter()
            index = _Index(db)
            pending = list(state.pending or [])
            last_id = int(state.last_event_id or 0)

            def event_id(event: Any) -> int:
                try:
                    return int(event.get("id"))
                except (AttributeError, TypeError, ValueError):
                    return -1

            for event in sorted((e for e in events if isinstance(e, dict)), key=event_id):
                current = event_id(event)
                if current < 0:
                    counts["invalid"] += 1
                    continue
                if current <= last_id:
                    counts["already_applied"] += 1
                    continue
                kind = str(event.get("type") or "")
                data = event.get("data")
                outcome = _apply_one(db, index, kind, data, counts)
                counts[outcome] += 1
                if isinstance(data, dict) and kind in RETRY_ORDER:
                    pending = _merge_pending(pending, kind, data, outcome)
                last_id = current
            if pending:
                pending = _retry_pending(db, index, pending, counts)

            now = utc_now_naive()
            state.last_event_id = last_id
            state.pending = pending
            result = {**dict(counts), "events": len(events), "pending": len(pending), "source": source}
            state.last_result = result
            if source == "push":
                state.last_push_at = now
            else:
                state.last_pull_at = now
            state.last_error = None
            state.last_error_at = None
            db.commit()
            return {"last_event_id": last_id, "result": result}
        except Exception as exc:
            logger.exception("EkLink sync batch failed")
            record_error(db, f"Applying EkLink changes failed ({type(exc).__name__})")
            raise


def apply_snapshot(db: Session, snapshot: dict) -> dict:
    """Full reconcile from EkLink's snapshot: directory (parents first), people,
    approver jobs. Nothing is deleted; linked users or EkLink jobs missing
    from the snapshot are only counted. Commits."""
    with _lock:
        try:
            state = get_state(db, lock=True)
            counts: Counter = Counter()
            index = _Index(db)
            pending: list[dict] = []
            directory = [d for d in snapshot.get("directory") or [] if isinstance(d, dict)]
            directory.sort(key=lambda d: LEVEL_ORDER.get(d.get("level"), 9))
            sections = (
                ("directory.upserted", directory),
                ("person.upserted", snapshot.get("people") or []),
                ("approver.upserted", snapshot.get("approvers") or []),
            )
            for kind, rows in sections:
                for data in rows:
                    if not isinstance(data, dict):
                        counts["invalid"] += 1
                        continue
                    outcome = _apply_one(db, index, kind, data, counts)
                    counts[f"{kind.split('.')[0]}_{outcome}"] += 1
                    if outcome == "unresolved":
                        pending = _merge_pending(pending, kind, data, outcome)
            if pending:
                pending = _retry_pending(db, index, pending, counts)

            subs = {_str(p, "sub", 64) for p in snapshot.get("people") or [] if isinstance(p, dict)}
            counts["linked_users_not_in_eklink"] = sum(
                1 for sub in index.users_by_sub if sub not in subs
            )
            job_ids = {
                _str(a, "id", 36) for a in snapshot.get("approvers") or [] if isinstance(a, dict)
            }
            counts["eklink_jobs_not_in_snapshot"] = sum(
                1 for key in index.approvers if key not in job_ids
            )

            now = utc_now_naive()
            try:
                state.last_event_id = int(snapshot.get("last_event_id") or 0)
            except (TypeError, ValueError):
                pass
            state.pending = pending
            result = {**dict(counts), "pending": len(pending), "source": "snapshot"}
            state.last_result = result
            state.last_full_sync_at = now
            state.last_pull_at = now
            state.last_error = None
            state.last_error_at = None
            db.commit()
            return {"last_event_id": state.last_event_id, "result": result}
        except Exception as exc:
            logger.exception("EkLink full resync failed")
            record_error(db, f"Applying the EkLink snapshot failed ({type(exc).__name__})")
            raise


# ── push: verify EkLink's signed batch ───────────────────────────────


def verify_events_jwt(token: str) -> list[dict]:
    """Events of a pushed batch after checking the ES256 signature (EkLink's
    JWKS), typ, iss, aud (= our client id) and exp. Raises SyncError."""
    if not settings.eklink_url or not settings.eklink_client_id:
        raise SyncError(503, "EkLink sync is not configured")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        raise SyncError(401, "The EkLink event batch is not a valid JWT") from None
    if header.get("typ") != EVENTS_JWT_TYPE or header.get("alg") != "ES256":
        raise SyncError(401, "The EkLink event batch has the wrong token type")
    try:
        key = eklink._jwks().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["ES256"],
            audience=settings.eklink_client_id,
            issuer=settings.eklink_issuer,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
    except jwt.PyJWKClientError:
        raise SyncError(502, "Could not load EkLink's signing keys") from None
    except jwt.InvalidTokenError:
        raise SyncError(401, "The EkLink event batch signature is invalid") from None
    events = claims.get("events")
    if not isinstance(events, list) or len(events) > MAX_EVENTS_PER_PUSH:
        raise SyncError(400, "The EkLink event batch has no valid events list")
    return events


def _first_new_id(db: Session, events: list[Any]) -> tuple[int, int | None]:
    last = int(get_state(db).last_event_id or 0)
    db.commit()
    ids = []
    for event in events:
        try:
            ids.append(int(event.get("id")))
        except (AttributeError, TypeError, ValueError):
            continue
    newer = [i for i in ids if i > last]
    return last, (min(newer) if newer else None)


def receive_push(db: Session, token: str) -> dict:
    events = verify_events_jwt(token)
    # A gap (an earlier delivery still failing) would be skipped for good once
    # a later id is stored, so catch up through the changes API first.
    last, first_new = _first_new_id(db, events)
    gap_missed = False
    if first_new is not None and first_new > last + 1 and settings.eklink_sync_configured:
        try:
            pull_changes(db)
        except SyncError as exc:
            gap_missed = True
            logger.warning("EkLink sync: catching up before a push failed: %s", exc.detail)
    try:
        outcome = apply_events(db, events, source="push")
    except Exception:
        raise SyncError(500, "Applying the EkLink events failed") from None
    if gap_missed:
        record_error(
            db,
            f"Events {last + 1}..{first_new - 1} were not received; run Full resync",
        )
    return outcome


# ── pull: TemplateOS asks EkLink ─────────────────────────────────────


def _require_pull_settings() -> None:
    if not settings.eklink_sync_configured:
        raise SyncError(503, "EkLink sync is not configured")


def _get(path: str, params: dict | None, timeout: float) -> dict:
    try:
        response = httpx.get(
            f"{settings.eklink_url}{path}",
            params=params,
            auth=httpx.BasicAuth(settings.eklink_client_id or "", settings.eklink_client_secret or ""),
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise SyncError(502, f"EkLink is not reachable ({type(exc).__name__})") from None
    if response.status_code == 401:
        raise SyncError(502, "EkLink rejected TemplateOS's client credentials")
    if response.status_code != 200:
        raise SyncError(502, f"EkLink answered {response.status_code} for {path}")
    try:
        body = response.json()
    except ValueError:
        raise SyncError(502, f"EkLink returned invalid JSON for {path}") from None
    if not isinstance(body, dict):
        raise SyncError(502, f"EkLink returned an unexpected body for {path}")
    return body


def pull_changes(db: Session) -> dict:
    """Fetch and apply every change after last_event_id (paged)."""
    _require_pull_settings()
    totals: Counter = Counter()
    pages = 0
    try:
        last_id = int(get_state(db).last_event_id or 0)
        db.commit()
        while pages < MAX_PULL_PAGES:
            body = _get("/api/sync/changes", {"after": last_id, "limit": PULL_PAGE_LIMIT}, PULL_TIMEOUT_SECONDS)
            events = body.get("events") or []
            if not isinstance(events, list):
                raise SyncError(502, "EkLink returned no events list")
            pages += 1
            outcome = apply_events(db, events, source="pull")
            for key, value in outcome["result"].items():
                if isinstance(value, int):
                    totals[key] += value
            last_id = outcome["last_event_id"]
            if not body.get("has_more") or not events:
                break
    except SyncError as exc:
        record_error(db, exc.detail)
        raise
    except Exception as exc:
        record_error(db, f"Sync failed ({type(exc).__name__})")
        raise SyncError(500, "Applying the EkLink changes failed") from None
    state = get_state(db)
    state.last_pull_at = utc_now_naive()
    result = {**dict(totals), "pages": pages, "source": "pull"}
    if pages:
        state.last_result = {**result, "pending": len(state.pending or [])}
    db.commit()
    return {"last_event_id": int(state.last_event_id or 0), "result": state.last_result or result}


def full_resync(db: Session) -> dict:
    """Snapshot reconcile, then the changes made since the snapshot."""
    _require_pull_settings()
    try:
        snapshot = _get("/api/sync/snapshot", None, SNAPSHOT_TIMEOUT_SECONDS)
        outcome = apply_snapshot(db, snapshot)
    except SyncError as exc:
        record_error(db, exc.detail)
        raise
    except Exception as exc:
        record_error(db, f"Full resync failed ({type(exc).__name__})")
        raise SyncError(500, "Applying the EkLink snapshot failed") from None
    result = outcome["result"]
    try:
        follow = pull_changes(db)
    except SyncError:
        follow = None
    state = get_state(db)
    if follow is not None and follow["result"].get("pages"):
        state.last_result = {**result, "followup": follow["result"]}
    else:
        state.last_result = result
    db.commit()
    return {"last_event_id": int(state.last_event_id or 0), "result": state.last_result}
