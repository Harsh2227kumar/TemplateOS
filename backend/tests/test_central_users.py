"""
Central users and roles: the institute level, deactivation, legacy roles,
EkLink sign-in sync, approver assignments, institute templates and the
public sign-up switch.

Cast (fresh in-memory database per test):

  SIU (code SIU)
    SIT (code SIT): CSE (code CSE), ECE (code ECE)
    SIBM (code SIBM): MBA (code MBA)
  Other (code OTH)
    OI: LAW
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.approver_assignment import ApproverAssignment
from app.models.organization import Department, Institute, Organization
from app.models.template import Template
from app.models.user import User
from app.services import eklink
from app.services.template_access import library_visibility_filter, user_can_view_template

test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
client = TestClient(app)
API = "/api/v1"


def override_get_db():
    with TestSession() as db:
        yield db


@pytest.fixture(scope="module", autouse=True)
def _override_db():
    old = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    yield
    if old is not None:
        app.dependency_overrides[get_db] = old
    else:
        app.dependency_overrides.pop(get_db, None)


# key: (role, member_type, org, institute, department)
PEOPLE = {
    "super": ("super_admin", None, None, None, None),
    "siu_admin": ("org_admin", None, "siu", None, None),
    "sit_admin": ("institute_admin", "faculty", "siu", "sit", None),
    "sibm_admin": ("institute_admin", None, "siu", "sibm", None),
    "cse_admin": ("department_admin", "faculty", "siu", "sit", "cse"),
    "cse_fac": ("faculty", "faculty", "siu", "sit", "cse"),
    "cse_staff": ("staff", "staff", "siu", "sit", "cse"),
    "cse_stu": ("student", "student", "siu", "sit", "cse"),
    "ece_fac": ("faculty", "faculty", "siu", "sit", "ece"),
    "mba_fac": ("faculty", "faculty", "siu", "sibm", "mba"),
    "law_fac": ("faculty", "faculty", "oth", "oi", "law"),
    "legacy": ("normal_user", "staff", "siu", "sit", "cse"),
}


@pytest.fixture()
def ids() -> dict[str, int]:
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    out: dict[str, int] = {}
    with TestSession() as s:
        for key, name, code in (("siu", "Symbiosis", "SIU"), ("oth", "Other", "OTH")):
            org = Organization(name=name, code=code)
            s.add(org)
            s.flush()
            out[key] = org.id
        for key, org, name, code in (
            ("sit", "siu", "SIT", "SIT"),
            ("sibm", "siu", "SIBM", "SIBM"),
            ("oi", "oth", "Other Institute", "OI"),
        ):
            inst = Institute(organization_id=out[org], name=name, code=code)
            s.add(inst)
            s.flush()
            out[key] = inst.id
        for key, org, inst, name, code in (
            ("cse", "siu", "sit", "Computer Science", "CSE"),
            ("ece", "siu", "sit", "Electronics", "ECE"),
            ("mba", "siu", "sibm", "MBA", "MBA"),
            ("law", "oth", "oi", "Law", "LAW"),
        ):
            dept = Department(
                organization_id=out[org], institute_id=out[inst], name=name, code=code
            )
            s.add(dept)
            s.flush()
            out[key] = dept.id
        for key, (role, member_type, org, inst, dept) in PEOPLE.items():
            user = User(
                email=f"{key}@central.example.com",
                full_name=key,
                role=role,
                member_type=member_type,
                hashed_password=hash_password("password123"),
                organization_id=out[org] if org else None,
                institute_id=out[inst] if inst else None,
                department_id=out[dept] if dept else None,
            )
            s.add(user)
            s.flush()
            out[key] = user.id
        s.commit()
    yield out
    Base.metadata.drop_all(bind=test_engine)


def _auth(ids, key):
    return {"Authorization": f"Bearer {create_access_token(str(ids[key]))}"}


def _patch(ids, actor, target, body):
    return client.patch(f"{API}/admin/users/{ids[target]}", json=body, headers=_auth(ids, actor))


def _user(user_id) -> User:
    with TestSession() as s:
        user = s.get(User, user_id)
        s.expunge(user)
        return user


# ── institute scope ──────────────────────────────────────────────────


def _listed_ids(ids, actor, **params):
    response = client.get(f"{API}/admin/users", params={"limit": 100, **params}, headers=_auth(ids, actor))
    assert response.status_code == 200, response.json()
    return {row["id"] for row in response.json()["users"]}


def test_institute_admin_sees_only_their_institute(ids):
    seen = _listed_ids(ids, "sit_admin")
    for key in ("sit_admin", "cse_admin", "cse_fac", "cse_stu", "ece_fac", "legacy"):
        assert ids[key] in seen
    for key in ("mba_fac", "law_fac", "siu_admin", "super", "sibm_admin"):
        assert ids[key] not in seen
    # org admin sees the whole organization, not the other one
    org_seen = _listed_ids(ids, "siu_admin")
    assert ids["mba_fac"] in org_seen and ids["law_fac"] not in org_seen


def test_role_ladder(ids):
    # institute admin may create department admins inside their institute ...
    assert _patch(ids, "sit_admin", "ece_fac", {"role": "department_admin", "department_id": ids["ece"]}).status_code == 200
    # ... but not another institute admin, and nothing outside the institute
    assert _patch(ids, "sit_admin", "cse_fac", {"role": "institute_admin"}).status_code == 403
    assert _patch(ids, "sit_admin", "mba_fac", {"role": "staff"}).status_code == 403
    # department admin: members only, inside the department
    assert _patch(ids, "cse_admin", "cse_stu", {"role": "staff"}).status_code == 200
    assert _patch(ids, "cse_admin", "cse_fac", {"role": "department_admin"}).status_code == 403
    # org admin may appoint institute admins in their organization
    assert _patch(ids, "siu_admin", "mba_fac", {"role": "institute_admin"}).status_code == 200
    assert _user(ids["mba_fac"]).institute_id == ids["sibm"]
    # a member role sets member_type
    assert _user(ids["cse_stu"]).member_type == "staff"


def test_moving_users_between_departments_and_institutes(ids):
    # institute admin moves inside their institute; the department keeps the institute
    assert _patch(ids, "sit_admin", "cse_fac", {"department_id": ids["ece"]}).status_code == 200
    moved = _user(ids["cse_fac"])
    assert (moved.department_id, moved.institute_id) == (ids["ece"], ids["sit"])
    # ... but cannot move someone into another institute's department
    assert _patch(ids, "sit_admin", "cse_stu", {"department_id": ids["mba"]}).status_code == 403
    # org admin moves across institutes; a department of the new institute is required to keep one
    assert _patch(ids, "siu_admin", "cse_stu", {"institute_id": ids["sibm"]}).status_code == 200
    stu = _user(ids["cse_stu"])
    assert (stu.institute_id, stu.department_id) == (ids["sibm"], None)
    # inconsistent placement is refused
    assert _patch(ids, "siu_admin", "cse_stu", {"institute_id": ids["sit"], "department_id": ids["mba"]}).status_code == 422


def test_admin_role_needs_its_scope(ids):
    no_place = {"institute_id": None, "department_id": None}
    assert _patch(ids, "super", "law_fac", {"role": "institute_admin", **no_place}).status_code == 422
    assert _patch(ids, "super", "law_fac", {"role": "department_admin", **no_place}).status_code == 422
    # a department implies its institute, so this one is fine
    assert _patch(ids, "super", "law_fac", {"role": "institute_admin"}).status_code == 200
    assert _user(ids["law_fac"]).institute_id == ids["oi"]


def test_legacy_role_can_be_converted_not_assigned(ids):
    assert _patch(ids, "cse_admin", "legacy", {"role": "normal_user"}).status_code == 422
    assert _patch(ids, "cse_admin", "cse_fac", {"role": "approver"}).status_code == 422
    assert _patch(ids, "cse_admin", "legacy", {"role": "staff"}).status_code == 200
    assert _user(ids["legacy"]).role == "staff"


# ── deactivation ─────────────────────────────────────────────────────


def _login(email):
    return client.post(f"{API}/auth/login", json={"email": email, "password": "password123"})


def test_deactivation_blocks_sign_in_and_keeps_the_user(ids):
    assert _login("cse_fac@central.example.com").status_code == 200
    token_headers = _auth(ids, "cse_fac")
    assert client.get(f"{API}/auth/me", headers=token_headers).status_code == 200

    assert _patch(ids, "cse_admin", "cse_fac", {"is_active": False}).status_code == 200
    assert _login("cse_fac@central.example.com").status_code == 403
    assert client.get(f"{API}/auth/me", headers=token_headers).status_code == 401
    assert _user(ids["cse_fac"]) is not None  # still there

    listed = client.get(f"{API}/admin/users", params={"is_active": False}, headers=_auth(ids, "cse_admin")).json()
    assert [row["id"] for row in listed["users"]] == [ids["cse_fac"]]

    assert _patch(ids, "cse_admin", "cse_fac", {"is_active": True}).status_code == 200
    assert _login("cse_fac@central.example.com").status_code == 200


def test_cannot_deactivate_self_or_last_super_admin(ids):
    assert _patch(ids, "cse_admin", "cse_admin", {"is_active": False}).status_code == 403
    assert _patch(ids, "super", "super", {"is_active": False}).status_code == 403
    # a second super admin cannot deactivate the only *other*... make one, then try the last
    assert _patch(ids, "super", "law_fac", {"role": "super_admin"}).status_code == 200
    assert _patch(ids, "law_fac", "super", {"is_active": False}).status_code == 200
    assert _patch(ids, "super", "law_fac", {"is_active": False}).status_code == 401  # super is inactive now


# ── directory: institutes and departments ────────────────────────────


def test_institute_and_department_management(ids):
    # SIU / SIT / CSE carry codes: they are mirrored from EkLink (read-only here)
    managed = client.post(f"{API}/admin/institutes", json={"name": "SLS"}, headers=_auth(ids, "siu_admin"))
    assert managed.status_code == 409 and "Managed in EkLink" in managed.json()["detail"]
    assert client.post(f"{API}/admin/departments", json={"name": "IT"}, headers=_auth(ids, "sit_admin")).status_code == 409
    assert client.patch(f"{API}/admin/departments/{ids['cse']}", json={"name": "X"}, headers=_auth(ids, "sit_admin")).status_code == 409
    assert client.delete(f"{API}/admin/institutes/{ids['sibm']}", headers=_auth(ids, "siu_admin")).status_code == 409
    # institute admins cannot create institutes; scope checks still come first
    assert client.post(f"{API}/admin/institutes", json={"name": "X"}, headers=_auth(ids, "sit_admin")).status_code == 403
    assert client.post(
        f"{API}/admin/departments", json={"name": "HR", "institute_id": ids["sibm"]}, headers=_auth(ids, "sit_admin")
    ).status_code == 403
    # codes are assigned by EkLink only
    assert client.post(f"{API}/admin/organizations", json={"name": "Coded", "code": "CDE"}, headers=_auth(ids, "super")).status_code == 409

    # local rows (no code) stay fully editable
    org = client.post(f"{API}/admin/organizations", json={"name": "Local U"}, headers=_auth(ids, "super"))
    assert org.status_code == 201 and org.json()["managed_by_eklink"] is False
    org_id = org.json()["id"]
    inst = client.post(f"{API}/admin/institutes", json={"name": "LI", "organization_id": org_id}, headers=_auth(ids, "super"))
    assert inst.status_code == 201, inst.json()
    inst_id = inst.json()["id"]
    inst2 = client.post(f"{API}/admin/institutes", json={"name": "LI2", "organization_id": org_id}, headers=_auth(ids, "super"))
    dept = client.post(f"{API}/admin/departments", json={"name": "Computer Science", "institute_id": inst_id}, headers=_auth(ids, "super"))
    assert dept.status_code == 201, dept.json()
    assert dept.json()["institute_id"] == inst_id and dept.json()["managed_by_eklink"] is False
    # the same department name is fine in another institute, not twice in one
    assert client.post(
        f"{API}/admin/departments", json={"name": "Computer Science", "institute_id": inst2.json()["id"]},
        headers=_auth(ids, "super"),
    ).status_code == 201
    assert client.post(
        f"{API}/admin/departments", json={"name": "computer science", "institute_id": inst_id},
        headers=_auth(ids, "super"),
    ).status_code == 409
    assert client.patch(f"{API}/admin/departments/{dept.json()['id']}", json={"name": "CS"}, headers=_auth(ids, "super")).status_code == 200
    assert client.patch(f"{API}/admin/departments/{dept.json()['id']}", json={"code": "CS"}, headers=_auth(ids, "super")).status_code == 409
    # an institute with departments cannot be deleted
    assert client.delete(f"{API}/admin/institutes/{inst_id}", headers=_auth(ids, "super")).status_code == 409
    assert client.delete(f"{API}/admin/departments/{dept.json()['id']}", headers=_auth(ids, "super")).status_code == 204
    assert client.delete(f"{API}/admin/institutes/{inst_id}", headers=_auth(ids, "super")).status_code == 204
    listed = client.get(f"{API}/admin/institutes", headers=_auth(ids, "sit_admin")).json()
    assert [row["id"] for row in listed] == [ids["sit"]]
    assert listed[0]["managed_by_eklink"] is True


# ── EkLink sign-in sync ──────────────────────────────────────────────


def _claims(**extra):
    base = {
        "sub": "11111111-2222-3333-4444-555555555555",
        "login_id": "24070521999",
        "email": "new.student@sitnagpur.siu.edu.in",
        "name": "New Student",
        "role": "student",
        "platform_role": "student",
        "org_code": "SIU",
        "institute_code": "SIT",
        "department_code": "CSE",
        "batch": "2024-28",
        "section": "A",
        "semester": 5,
    }
    base.update(extra)
    return base


def test_sync_creates_and_places_a_new_user(ids):
    with TestSession() as s:
        user = eklink.sync_user(s, _claims())
        s.commit()
        assert (user.role, user.member_type) == ("student", "student")
        assert (user.organization_id, user.institute_id, user.department_id) == (ids["siu"], ids["sit"], ids["cse"])
        assert (user.login_id, user.batch, user.section, user.semester) == ("24070521999", "2024-28", "A", 5)
        assert user.hashed_password is None and user.sso


def test_sync_links_existing_user_by_email_and_updates(ids):
    with TestSession() as s:
        user = eklink.sync_user(s, _claims(email="cse_fac@central.example.com", login_id="T999",
                                           name="Dr. Renamed", role="faculty", platform_role="faculty",
                                           department_code="ECE"))
        s.commit()
        assert user.id == ids["cse_fac"]
        assert (user.login_id, user.full_name, user.department_id) == ("T999", "Dr. Renamed", ids["ece"])
        # next sign-in matches by eklink_sub even if the email changed
        again = eklink.sync_user(s, _claims(email="changed@sitnagpur.siu.edu.in", login_id="T999",
                                            role="faculty", platform_role="faculty"))
        assert again.id == ids["cse_fac"] and again.email == "changed@sitnagpur.siu.edu.in"


def test_sync_never_lowers_an_admin_role(ids):
    with TestSession() as s:
        user = eklink.sync_user(s, _claims(email="cse_admin@central.example.com", login_id="T100",
                                           role="hod", platform_role="faculty"))
        assert user.role == "department_admin"
        assert user.member_type == "faculty"
        # an EkLink admin role is applied (super admin from EkLink)
        boss = eklink.sync_user(s, _claims(sub="99999999-2222-3333-4444-555555555555",
                                           email="cse_stu@central.example.com", login_id="SU-ADMIN001",
                                           role="admin", platform_role="super_admin"))
        assert boss.role == "super_admin"


def test_sync_refuses_inactive_and_conflicting_accounts(ids):
    with TestSession() as s:
        s.get(User, ids["cse_stu"]).is_active = False
        s.commit()
        with pytest.raises(eklink.EklinkError) as inactive:
            eklink.sync_user(s, _claims(email="cse_stu@central.example.com"))
        assert inactive.value.status_code == 403
        first = eklink.sync_user(s, _claims())
        s.commit()
        with pytest.raises(eklink.EklinkError) as conflict:
            eklink.sync_user(s, _claims(sub="00000000-0000-0000-0000-000000000000",
                                        login_id="24070521999", email="x@y.z"))
        assert conflict.value.status_code == 409
        assert first.eklink_sub == _claims()["sub"]


def test_sync_old_tokens_without_codes_still_work(ids):
    legacy_claims = {k: v for k, v in _claims().items()
                     if k not in ("platform_role", "org_code", "institute_code", "department_code")}
    legacy_claims["role"] = "director"
    with TestSession() as s:
        user = eklink.sync_user(s, legacy_claims)
        assert (user.role, user.member_type) == ("faculty", "faculty")
        assert user.organization_id is None  # EKLINK_ORGANIZATION unset in tests


# ── approver assignments ─────────────────────────────────────────────


def _assign(ids, actor, user, **body):
    payload = {"user_id": ids[user], "title": "HOD", "scope_level": "department",
               "department_id": ids["cse"], **body}
    return client.post(f"{API}/admin/approvers", json=payload, headers=_auth(ids, actor))


def test_approver_assignments(ids):
    created = _assign(ids, "sit_admin", "cse_fac")
    assert created.status_code == 201, created.json()
    body = created.json()
    assert body["is_current"] and body["scope_name"] == "Computer Science" and body["valid_to"] is None
    # staff can be approvers too; students cannot
    assert _assign(ids, "cse_admin", "cse_staff", title="Exam Cell").status_code == 201
    assert _assign(ids, "cse_admin", "cse_stu").status_code == 422
    # out of scope
    assert _assign(ids, "cse_admin", "mba_fac", department_id=ids["mba"]).status_code == 403
    assert _assign(ids, "cse_admin", "cse_fac", title="Director", scope_level="institute",
                   department_id=None, institute_id=ids["sit"]).status_code == 403
    # the approver must belong to the scope
    assert _assign(ids, "siu_admin", "mba_fac").status_code == 422
    # institute-level job by an institute admin
    assert _assign(ids, "sit_admin", "sit_admin", title="Director", scope_level="institute",
                   department_id=None, institute_id=ids["sit"]).status_code == 201

    listed = client.get(f"{API}/admin/approvers", headers=_auth(ids, "cse_admin")).json()
    assert {row["title"] for row in listed["assignments"]} == {"HOD", "Exam Cell"}

    ended = client.post(f"{API}/admin/approvers/{body['id']}/end", headers=_auth(ids, "cse_admin"))
    assert ended.status_code == 200 and ended.json()["valid_to"] is not None
    with TestSession() as s:
        assert s.get(ApproverAssignment, body["id"]) is not None  # ended, not deleted
    # members cannot manage approvers
    assert client.get(f"{API}/admin/approvers", headers=_auth(ids, "cse_fac")).status_code == 403


# ── institute templates ──────────────────────────────────────────────


def _template(s, ids, uploader, visibility, **scope) -> Template:
    template = Template(name=f"{visibility}-{uploader}", category="notice", visibility=visibility,
                        uploaded_by=ids[uploader], **scope)
    s.add(template)
    s.flush()
    return template


def test_institute_template_visibility_and_parity(ids):
    with TestSession() as s:
        inst_t = _template(s, ids, "sit_admin", "institute", scope_organization_id=ids["siu"],
                           scope_institute_id=ids["sit"])
        dept_t = _template(s, ids, "cse_admin", "department", scope_organization_id=ids["siu"],
                           scope_institute_id=ids["sit"], scope_department_id=ids["cse"])
        s.commit()
        for key in PEOPLE:
            user = s.get(User, ids[key])
            sql = library_visibility_filter(user)
            query = select(Template.id)
            if sql is not None:
                query = query.where(sql)
            visible_sql = set(s.scalars(query).all())
            visible_py = {t.id for t in (inst_t, dept_t) if user_can_view_template(user, t)}
            assert visible_py == visible_sql & {inst_t.id, dept_t.id}, key
        sees = lambda key, t: user_can_view_template(s.get(User, ids[key]), t)
        assert sees("ece_fac", inst_t) and not sees("ece_fac", dept_t)
        assert not sees("mba_fac", inst_t) and not sees("law_fac", inst_t)
        assert sees("siu_admin", dept_t)


def test_institute_admin_publishes_to_institute(ids):
    options = client.get(f"{API}/templates/access-options", headers=_auth(ids, "sit_admin")).json()
    assert options["can_publish"] == {"organization": False, "institute": True, "department": True}
    assert [row["id"] for row in options["institutes"]] == [ids["sit"]]
    assert {row["id"] for row in options["departments"]} == {ids["cse"], ids["ece"]}


# ── public sign-up switch ────────────────────────────────────────────


def test_signup_can_be_turned_off(ids, monkeypatch):
    monkeypatch.setattr(settings, "allow_public_signup", False)
    response = client.post(f"{API}/auth/signup", json={
        "full_name": "Someone", "email": "someone@example.com", "password": "password123"})
    assert response.status_code == 403
    assert client.get(f"{API}/auth/eklink").json()["signup_enabled"] is False
