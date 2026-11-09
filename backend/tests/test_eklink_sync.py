"""
EkLink change sync (SYNC_CONTRACT.md): signed push endpoint, every event
type, ordering / idempotency, deactivation ending sessions, pending codes,
pull + snapshot through a faked EkLink, the admin sync endpoints and the
"Managed in EkLink" ownership rules.

EkLink is faked: the JWKS client (an ES256 key generated here) and httpx.get.
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import ACCESS_COOKIE_NAME, create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.approver_assignment import ApproverAssignment
from app.models.organization import Department, Institute, Organization
from app.models.refresh_token import RefreshToken
from app.models.sync_state import SyncState
from app.models.user import User
from app.services import eklink, eklink_scheduler, eklink_sync

API = settings.api_v1_prefix
PUSH = f"{API}/sync/eklink/events"
EKLINK_URL = "http://eklink.test"
CLIENT_ID = "templateos_test"
SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())

test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


def _override_get_db():
    with TestSession() as db:
        yield db


@pytest.fixture(autouse=True)
def database():
    old = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    if old is not None:
        app.dependency_overrides[get_db] = old
    else:
        app.dependency_overrides.pop(get_db, None)


class FakeEklink:
    """Answers GET /api/sync/changes and /api/sync/snapshot."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.snapshot: dict = {"last_event_id": 0, "directory": [], "people": [], "approvers": []}
        self.calls: list[tuple[str, dict | None, object]] = []
        self.fail = False

    def get(self, url, params=None, auth=None, timeout=None):
        self.calls.append((url, params, auth))
        if self.fail:
            raise httpx.ConnectError("down")
        if url.endswith("/api/sync/changes"):
            after = int(params["after"])
            page = [e for e in self.events if e["id"] > after][: int(params["limit"])]
            last = page[-1]["id"] if page else after
            return httpx.Response(200, json={"events": page, "last_event_id": last, "has_more": False})
        if url.endswith("/api/sync/snapshot"):
            return httpx.Response(200, json=self.snapshot)
        return httpx.Response(404, json={})


@pytest.fixture(autouse=True)
def eklink_settings(monkeypatch):
    monkeypatch.setattr(settings, "eklink_url", EKLINK_URL)
    monkeypatch.setattr(settings, "eklink_issuer_setting", None)
    monkeypatch.setattr(settings, "eklink_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "eklink_client_secret", "client-secret")
    monkeypatch.setattr(settings, "eklink_sync_enabled_setting", True)
    monkeypatch.setattr(
        eklink,
        "_jwks",
        lambda: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=SIGNING_KEY.public_key())
        ),
    )


@pytest.fixture()
def fake(monkeypatch) -> FakeEklink:
    server = FakeEklink()
    monkeypatch.setattr(eklink_sync.httpx, "get", server.get)
    return server


@pytest.fixture()
def client(fake):
    with TestClient(app) as test_client:
        yield test_client


# ── builders ─────────────────────────────────────────────────────────


def _batch(events, key=SIGNING_KEY, typ="eklink-events+jwt", **overrides) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "iss": EKLINK_URL,
        "aud": CLIENT_ID,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "jti": str(uuid.uuid4()),
        "events": events,
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="ES256", headers={"kid": "k1", "typ": typ})


def _push(client, events, **kwargs):
    return client.post(PUSH, content=_batch(events, **kwargs), headers={"Content-Type": "application/jwt"})


def _event(event_id, kind, data):
    return {"id": event_id, "type": kind, "at": "2026-11-09T10:00:00Z", "data": data}


SUB = "11111111-2222-3333-4444-555555555555"


def _person(**extra):
    data = {
        "sub": SUB, "login_id": "T004", "email": "t004@sitnagpur.siu.edu.in", "name": "Dr. Four",
        "role": "hod", "platform_role": "faculty", "member_type": "faculty",
        "org_code": "SIU", "institute_code": "SIT", "department_code": "CSE",
        "batch": None, "section": None, "semester": None, "designation": None,
        "is_active": True, "is_demo": False,
    }
    data.update(extra)
    return data


def _dir(level, code, name, org_code=None, institute_code=None, **extra):
    data = {"level": level, "code": code, "name": name, "org_code": org_code,
            "institute_code": institute_code, "is_active": True, "is_demo": False}
    data.update(extra)
    return data


SIU_DIRECTORY = [
    _dir("organization", "SIU", "Symbiosis International University", "SIU"),
    _dir("institute", "SIT", "SIT Nagpur", "SIU", "SIT"),
    _dir("department", "CSE", "Computer Science and Engineering", "SIU", "SIT"),
]


def _approver(**extra):
    data = {"id": "aaaaaaaa-0000-0000-0000-000000000001", "person_sub": SUB, "login_id": "T004",
            "title": "HOD", "scope_level": "department", "org_code": "SIU", "institute_code": "SIT",
            "department_code": "CSE", "scope_key": None, "valid_from": "2026-11-09", "valid_to": None}
    data.update(extra)
    return data


def _seed_directory() -> dict:
    with TestSession() as s:
        org = Organization(name="Symbiosis International University", code="SIU")
        s.add(org)
        s.flush()
        inst = Institute(organization_id=org.id, name="SIT Nagpur", code="SIT")
        s.add(inst)
        s.flush()
        dept = Department(organization_id=org.id, institute_id=inst.id, name="CSE", code="CSE")
        local_org = Organization(name="Local Org")
        s.add_all([dept, local_org])
        s.flush()
        out = {"siu": org.id, "sit": inst.id, "cse": dept.id, "local": local_org.id}
        s.commit()
        return out


def _add_user(email, role="super_admin", **fields) -> int:
    with TestSession() as s:
        user = User(email=email, full_name=email, role=role,
                    hashed_password=hash_password("password123"), **fields)
        s.add(user)
        s.commit()
        return user.id


def _auth(user_id):
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


def _state() -> SyncState:
    with TestSession() as s:
        state = s.get(SyncState, 1)
        s.expunge(state)
        return state


def _user_by(login_id=None, sub=None) -> User | None:
    with TestSession() as s:
        query = select(User)
        query = query.where(User.login_id == login_id) if login_id else query.where(User.eklink_sub == sub)
        user = s.scalar(query)
        if user is not None:
            s.expunge(user)
        return user


# ── push verification ────────────────────────────────────────────────


def test_push_applies_events_and_reports_last_id(client):
    response = _push(client, [_event(1, "directory.upserted", d) for d in SIU_DIRECTORY[:1]]
                     + [_event(2, "directory.upserted", SIU_DIRECTORY[1]),
                        _event(3, "directory.upserted", SIU_DIRECTORY[2]),
                        _event(4, "person.upserted", _person())])
    assert response.status_code == 200, response.json()
    assert response.json() == {"last_event_id": 4}
    user = _user_by(login_id="T004")
    assert user.eklink_sub == SUB and user.role == "faculty" and user.member_type == "faculty"
    assert user.department_name == "Computer Science and Engineering"
    state = _state()
    assert state.last_event_id == 4 and state.last_push_at is not None
    assert state.last_result["applied"] == 4 and state.last_result["source"] == "push"


@pytest.mark.parametrize(
    "token_kwargs",
    [
        {"key": OTHER_KEY},
        {"typ": "JWT"},
        {"aud": "someone-else"},
        {"iss": "http://evil.test"},
        {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
    ],
)
def test_push_rejects_bad_tokens(client, token_kwargs):
    response = _push(client, [_event(1, "person.upserted", _person())], **token_kwargs)
    assert response.status_code == 401
    assert _user_by(login_id="T004") is None


def test_push_rejects_garbage_and_needs_no_csrf_or_cookie(client):
    assert client.post(PUSH, content="not-a-jwt", headers={"Content-Type": "application/jwt"}).status_code == 401
    assert client.post(PUSH, content="").status_code == 401
    # a browser session cookie does not trigger the CSRF check here, and is not the auth
    client.cookies.set(ACCESS_COOKIE_NAME, "whatever")
    ok = _push(client, [_event(1, "unknown.type", {})])
    assert ok.status_code == 200 and ok.json() == {"last_event_id": 1}


def test_push_is_refused_when_sync_is_switched_off(client, monkeypatch):
    monkeypatch.setattr(settings, "eklink_sync_enabled_setting", False)
    assert _push(client, [_event(1, "unknown.type", {})]).status_code == 503


# ── ordering and idempotency ─────────────────────────────────────────


def test_events_apply_in_order_skip_old_ids_and_unknown_types(client):
    _seed_directory()
    # out of order inside the batch: id 2 (rename) must win over id 1
    response = _push(client, [
        _event(2, "person.upserted", _person(name="Second")),
        _event(1, "person.upserted", _person(name="First")),
        _event(3, "something.new", {"x": 1}),
    ])
    assert response.json() == {"last_event_id": 3}
    assert _user_by(login_id="T004").full_name == "Second"
    # replaying the same ids changes nothing
    again = _push(client, [_event(1, "person.upserted", _person(name="Old"))])
    assert again.json() == {"last_event_id": 3}
    assert _user_by(login_id="T004").full_name == "Second"
    assert _state().last_result["already_applied"] == 1
    with TestSession() as s:
        assert len(s.scalars(select(User)).all()) == 1


def test_a_gap_is_filled_from_the_changes_api(client, fake):
    _seed_directory()
    fake.events = [_event(1, "person.upserted", _person(semester=3))]
    response = _push(client, [_event(2, "person.upserted", _person(login_id="T004", batch="2024"))])
    assert response.json() == {"last_event_id": 2}
    user = _user_by(login_id="T004")
    assert user.semester == 3 and user.batch == "2024"  # event 1 came from the pull
    assert fake.calls and fake.calls[0][1]["after"] == 0


# ── people ───────────────────────────────────────────────────────────


def test_person_upsert_links_existing_users_and_keeps_admin_roles(client):
    ids = _seed_directory()
    demo = _add_user("faculty@example.com", role="org_admin", organization_id=ids["local"])
    _push(client, [_event(1, "person.upserted", _person(
        sub="demo-sub", login_id="DEMO-FAC", email="Faculty@Example.com", name="Demo Faculty",
        role="faculty", platform_role="faculty", is_demo=True,
    ))])
    user = _user_by(login_id="DEMO-FAC")
    assert user.id == demo and user.eklink_sub == "demo-sub" and user.is_demo
    assert user.role == "org_admin"  # a TemplateOS admin role is never lowered
    assert user.organization_id == ids["siu"] and user.department_id == ids["cse"]
    # an EkLink admin role is applied
    _push(client, [_event(2, "person.upserted", _person(platform_role="super_admin", role="admin"))])
    assert _user_by(login_id="T004").role == "super_admin"


def test_deactivation_revokes_sessions_and_reactivation_works(client):
    _seed_directory()
    _push(client, [_event(1, "person.upserted", _person())])
    user = _user_by(login_id="T004")
    with TestSession() as s:
        s.add(RefreshToken(user_id=user.id, token_hash="h" * 64, family_id="f1",
                           expires_at=datetime(2099, 1, 1)))
        s.commit()
    headers = _auth(user.id)
    assert client.get(f"{API}/auth/me", headers=headers).status_code == 200

    _push(client, [_event(2, "person.upserted", _person(is_active=False))])
    assert _user_by(login_id="T004").is_active is False
    assert client.get(f"{API}/auth/me", headers=headers).status_code == 401
    with TestSession() as s:
        tokens = s.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id)).all()
        assert tokens and all(t.revoked_at is not None for t in tokens)
    assert _state().last_result["deactivated"] == 1

    _push(client, [_event(3, "person.upserted", _person(is_active=True))])
    assert _user_by(login_id="T004").is_active is True


def test_login_id_change(client):
    _seed_directory()
    _push(client, [_event(1, "person.upserted", _person(login_id="ADMIN001"))])
    _push(client, [_event(2, "person.login_id_changed",
                          {"sub": SUB, "old_login_id": "ADMIN001", "new_login_id": "SU-ADMIN001"})])
    assert _user_by(sub=SUB).login_id == "SU-ADMIN001"


def test_unknown_codes_are_kept_pending_and_resolved_later(client):
    # the person and the job arrive before their department exists
    _push(client, [
        _event(1, "person.upserted", _person()),
        _event(2, "approver.upserted", _approver()),
    ])
    user = _user_by(login_id="T004")
    assert user is not None and user.organization_id is None
    state = _state()
    assert state.last_event_id == 2 and len(state.pending) == 2
    _push(client, [_event(3 + n, "directory.upserted", d) for n, d in enumerate(SIU_DIRECTORY)])
    user = _user_by(login_id="T004")
    assert user.department_name == "Computer Science and Engineering"
    assert _state().pending == []
    with TestSession() as s:
        job = s.scalar(select(ApproverAssignment))
        assert job.source == "eklink" and job.user_id == user.id and job.title == "HOD"


# ── directory ────────────────────────────────────────────────────────


def test_directory_creates_adopts_renames_and_never_deletes(client):
    with TestSession() as s:
        demo = Organization(name="TemplateOS Demo Institute")
        s.add(demo)
        s.commit()
        demo_id = demo.id
    _push(client, [
        _event(1, "directory.upserted", _dir("organization", "DEMO", "TemplateOS Demo Institute", "DEMO", is_demo=True)),
        _event(2, "directory.upserted", _dir("institute", "DEMO-INST", "Demo Inst", "DEMO", "DEMO-INST")),
        _event(3, "directory.upserted", _dir("department", "CS", "Computer Science", "DEMO", "DEMO-INST")),
    ])
    with TestSession() as s:
        org = s.get(Organization, demo_id)
        assert org.code == "DEMO" and org.is_demo  # adopted by name, not duplicated
        assert len(s.scalars(select(Organization)).all()) == 1
        inst = s.scalar(select(Institute))
        assert (inst.code, inst.name) == ("DEMO-INST", "Demo Inst")
        dept = s.scalar(select(Department))
        assert (dept.code, dept.institute_id) == ("CS", inst.id)
    _push(client, [
        _event(4, "directory.upserted", _dir("department", "CS", "Computer Sciences", "DEMO", "DEMO-INST", is_active=False)),
    ])
    with TestSession() as s:
        dept = s.scalar(select(Department))
        assert dept.name == "Computer Sciences" and dept.is_active is False
        assert len(s.scalars(select(Department)).all()) == 1


# ── approver jobs ────────────────────────────────────────────────────


def test_approver_upsert_adopts_local_row_and_ends(client):
    ids = _seed_directory()
    _push(client, [_event(1, "person.upserted", _person())])
    user = _user_by(login_id="T004")
    with TestSession() as s:
        s.add(ApproverAssignment(user_id=user.id, title="HOD", scope_level="department",
                                 organization_id=ids["siu"], institute_id=ids["sit"],
                                 department_id=ids["cse"], valid_from=date(2026, 1, 1)))
        s.commit()
    _push(client, [_event(2, "approver.upserted", _approver())])
    with TestSession() as s:
        rows = s.scalars(select(ApproverAssignment)).all()
        assert len(rows) == 1 and rows[0].source == "eklink"
        assert rows[0].eklink_id == _approver()["id"]
    _push(client, [_event(3, "approver.upserted", _approver(valid_to="2026-11-10"))])
    _push(client, [_event(4, "approver.upserted", _approver(
        id="aaaaaaaa-0000-0000-0000-000000000002", title="Director", scope_level="institute",
        department_code=None))])
    with TestSession() as s:
        rows = {r.title: r for r in s.scalars(select(ApproverAssignment)).all()}
        assert rows["HOD"].valid_to == date(2026, 11, 10)
        assert rows["Director"].institute_id == ids["sit"] and rows["Director"].department_id is None


# ── pull and snapshot ────────────────────────────────────────────────


def _super(ids=None) -> int:
    return _add_user("root@example.com", role="super_admin")


def test_admin_sync_endpoints(client, fake):
    _seed_directory()
    root = _super()
    org_admin = _add_user("org@example.com", role="org_admin")
    member = _add_user("m@example.com", role="faculty")

    status = client.get(f"{API}/admin/sync/status", headers=_auth(org_admin))
    assert status.status_code == 200
    body = status.json()
    assert body["enabled"] and body["can_run"] is False
    assert body["eklink_admin_url"] == f"{EKLINK_URL}/admin"
    assert body["links"]["users"] == f"{EKLINK_URL}/admin/users"
    assert client.get(f"{API}/admin/sync/status", headers=_auth(member)).status_code == 403
    assert client.get(f"{API}/admin/sync/status").status_code == 401
    assert client.post(f"{API}/admin/sync/run", headers=_auth(org_admin)).status_code == 403
    assert client.post(f"{API}/admin/sync/full", headers=_auth(org_admin)).status_code == 403

    fake.events = [_event(7, "person.upserted", _person())]
    ran = client.post(f"{API}/admin/sync/run", headers=_auth(root))
    assert ran.status_code == 200, ran.json()
    assert ran.json()["last_event_id"] == 7 and ran.json()["status"]["can_run"] is True
    url, params, auth = fake.calls[-1]
    assert url == f"{EKLINK_URL}/api/sync/changes" and params == {"after": 0, "limit": 500}
    assert isinstance(auth, httpx.BasicAuth)
    assert _user_by(login_id="T004") is not None

    fake.snapshot = {
        "last_event_id": 20,
        "directory": list(reversed(SIU_DIRECTORY)),  # parents are applied first anyway
        "people": [_person(name="Snap Name"), _person(sub="s2", login_id="S2", email="s2@x.edu",
                                                      platform_role="student", role="student",
                                                      member_type="student")],
        "approvers": [_approver()],
    }
    full = client.post(f"{API}/admin/sync/full", headers=_auth(root))
    assert full.status_code == 200, full.json()
    status = full.json()["status"]
    assert status["last_event_id"] == 20 and status["last_full_sync_at"] is not None
    assert _user_by(login_id="T004").full_name == "Snap Name"
    assert _user_by(login_id="S2").role == "student"
    with TestSession() as s:
        assert s.scalar(select(ApproverAssignment)).source == "eklink"

    # EkLink down: 502 with a readable message, stored as last_error
    fake.fail = True
    down = client.post(f"{API}/admin/sync/run", headers=_auth(root))
    assert down.status_code == 502 and "not reachable" in down.json()["detail"]
    assert "not reachable" in client.get(f"{API}/admin/sync/status", headers=_auth(root)).json()["last_error"]


def test_run_needs_configuration(client, monkeypatch):
    root = _super()
    monkeypatch.setattr(settings, "eklink_client_secret", None)
    assert client.post(f"{API}/admin/sync/run", headers=_auth(root)).status_code == 503
    body = client.get(f"{API}/admin/sync/status", headers=_auth(root)).json()
    assert body["enabled"] is False and body["can_run"] is False


def test_scheduler_is_off_in_tests_and_schedules_daily():
    assert eklink_scheduler.scheduler_enabled() is False
    now = datetime(2026, 11, 9, 1, 30)
    assert eklink_scheduler.next_full_sync(now, "02:00") == datetime(2026, 11, 9, 2, 0)
    assert eklink_scheduler.next_full_sync(datetime(2026, 11, 9, 2, 0), "02:00") == datetime(2026, 11, 10, 2, 0)


# ── ownership ("Managed in EkLink") ──────────────────────────────────


def test_linked_users_placement_is_read_only(client):
    ids = _seed_directory()
    root = _super()
    _push(client, [_event(1, "person.upserted", _person())])
    target = _user_by(login_id="T004")
    url = f"{API}/admin/users/{target.id}"

    listed = client.get(f"{API}/admin/users", headers=_auth(root)).json()["users"]
    assert {u["login_id"]: u["managed_by_eklink"] for u in listed} == {"T004": True, None: False}

    for body in ({"department_id": None}, {"organization_id": ids["local"]},
                 {"member_type": "staff"}, {"is_active": False}, {"role": "staff"}):
        response = client.patch(url, json=body, headers=_auth(root))
        assert response.status_code == 409, body
        assert "Managed in EkLink" in response.json()["detail"]
    # unchanged values are fine, admin roles stay a TemplateOS decision
    assert client.patch(url, json={"department_id": ids["cse"], "is_active": True}, headers=_auth(root)).status_code == 200
    assert client.patch(url, json={"role": "department_admin"}, headers=_auth(root)).status_code == 200
    assert client.patch(url, json={"role": "faculty"}, headers=_auth(root)).status_code == 200
    # local users stay fully editable
    local = _add_user("local@example.com", role="staff", member_type="staff")
    assert client.patch(f"{API}/admin/users/{local}", json={"role": "student"}, headers=_auth(root)).status_code == 200

    # the profile name comes from EkLink
    me = client.patch(f"{API}/auth/me", json={"full_name": "Someone Else"}, headers=_auth(target.id))
    assert me.status_code == 409
    assert client.patch(f"{API}/auth/me", json={"phone": "123"}, headers=_auth(target.id)).status_code == 200
    assert client.get(f"{API}/auth/me", headers=_auth(target.id)).json()["managed_by_eklink"] is True


def test_approver_ownership(client, monkeypatch):
    ids = _seed_directory()
    root = _super()
    _push(client, [_event(1, "person.upserted", _person()), _event(2, "approver.upserted", _approver())])
    listed = client.get(f"{API}/admin/approvers", headers=_auth(root)).json()
    assert listed["can_create"] is False
    row = listed["assignments"][0]
    assert row["source"] == "eklink" and row["managed_by_eklink"] is True
    assert client.post(f"{API}/admin/approvers/{row['id']}/end", headers=_auth(root)).status_code == 409
    payload = {"user_id": row["user_id"], "title": "Exam Cell", "scope_level": "department",
               "department_id": ids["cse"]}
    created = client.post(f"{API}/admin/approvers", json=payload, headers=_auth(root))
    assert created.status_code == 409 and created.json()["detail"] == "Assign approvers in EkLink"
    # without sync, local assignments can be made and ended again
    monkeypatch.setattr(settings, "eklink_sync_enabled_setting", False)
    created = client.post(f"{API}/admin/approvers", json=payload, headers=_auth(root))
    assert created.status_code == 201 and created.json()["source"] == "local"
    assert client.post(f"{API}/admin/approvers/{created.json()['id']}/end", headers=_auth(root)).status_code == 200


def test_directory_rows_with_codes_are_read_only(client):
    ids = _seed_directory()
    root = _super()
    orgs = {o["id"]: o for o in client.get(f"{API}/admin/organizations", headers=_auth(root)).json()}
    assert orgs[ids["siu"]]["managed_by_eklink"] and not orgs[ids["local"]]["managed_by_eklink"]
    assert client.patch(f"{API}/admin/organizations/{ids['siu']}", json={"is_active": False}, headers=_auth(root)).status_code == 409
    assert client.delete(f"{API}/admin/organizations/{ids['siu']}", headers=_auth(root)).status_code == 409
    assert client.patch(f"{API}/admin/institutes/{ids['sit']}", json={"name": "X"}, headers=_auth(root)).status_code == 409
    assert client.delete(f"{API}/admin/departments/{ids['cse']}", headers=_auth(root)).status_code == 409
    assert client.post(f"{API}/admin/departments", json={"name": "New", "institute_id": ids["sit"]}, headers=_auth(root)).status_code == 409
    assert client.patch(f"{API}/admin/organizations/{ids['local']}", json={"name": "Local Renamed"}, headers=_auth(root)).status_code == 200
    assert client.patch(f"{API}/admin/organizations/{ids['local']}", json={"code": "LOC"}, headers=_auth(root)).status_code == 409
