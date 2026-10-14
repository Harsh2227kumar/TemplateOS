"""
User management (/admin/users), the organization / department directory
(/admin/organizations, /admin/departments) and self-service PATCH /auth/me.

Every test gets a fresh in-memory database with this cast:

  State University (uni): Computer Science (cs), Mechanical (me), Physics (phys)
  Other College (other): Law (law)
  Empty Institute (empty): Unused (unused)   <- nothing references it
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

from app.core.security import ACCESS_COOKIE_NAME, create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.organization import Department, Organization
from app.models.template import Template
from app.models.user import User
from app.services.user_admin import UserAdminError, apply_user_update

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


def override_get_db():
    with TestSession() as db:
        yield db


client = TestClient(app)

ORGS = {"uni": "State University", "other": "Other College", "empty": "Empty Institute"}
DEPTS = {
    "cs": ("uni", "Computer Science"),
    "me": ("uni", "Mechanical"),
    "phys": ("uni", "Physics"),
    "law": ("other", "Law"),
    "unused": ("empty", "Unused"),
}
# key: (role, org key, dept key)
PEOPLE = {
    "super": ("super_admin", None, None),
    "uni_admin": ("org_admin", "uni", None),
    "uni_admin2": ("org_admin", "uni", None),
    "other_admin": ("org_admin", "other", None),
    "cs_admin": ("department_admin", "uni", "cs"),
    "me_admin": ("department_admin", "uni", "me"),
    "cs_fac": ("faculty", "uni", "cs"),
    "cs_stu": ("student", "uni", "cs"),
    "me_fac": ("faculty", "uni", "me"),
    "law_fac": ("faculty", "other", "law"),
    "newbie": ("normal_user", None, None),
}


@pytest.fixture(scope="module", autouse=True)
def _override_db():
    old = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    yield
    if old is not None:
        app.dependency_overrides[get_db] = old
    else:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def ids() -> dict[str, int]:
    """Fresh schema + cast; returns ids for orgs, departments and users."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    out: dict[str, int] = {}
    with TestSession() as session:
        for key, name in ORGS.items():
            org = Organization(name=name)
            session.add(org)
            session.flush()
            out[key] = org.id
        for key, (org_key, name) in DEPTS.items():
            dept = Department(organization_id=out[org_key], name=name)
            session.add(dept)
            session.flush()
            out[key] = dept.id
        for key, (role, org_key, dept_key) in PEOPLE.items():
            user = User(
                email=f"{key}@admin.example.com",
                full_name=key,
                role=role,
                organization_id=out[org_key] if org_key else None,
                department_id=out[dept_key] if dept_key else None,
                organization=ORGS[org_key] if org_key else None,
                department=DEPTS[dept_key][1] if dept_key else None,
            )
            session.add(user)
            session.flush()
            out[key] = user.id
        session.commit()
    yield out
    Base.metadata.drop_all(bind=test_engine)


def _auth(ids, key):
    return {"Authorization": f"Bearer {create_access_token(str(ids[key]))}"}


def _patch_user(ids, actor, target, body):
    return client.patch(f"/api/v1/admin/users/{ids[target]}", json=body, headers=_auth(ids, actor))


def _user(user_id) -> User:
    with TestSession() as session:
        user = session.get(User, user_id)
        session.expunge(user)
        return user


# ── GET /admin/users ─────────────────────────────────────────────────


def _listed(ids, actor, **params):
    response = client.get("/api/v1/admin/users", params=params, headers=_auth(ids, actor))
    assert response.status_code == 200, response.json()
    return response.json()


def test_list_scopes(ids):
    everyone = _listed(ids, "super", limit=100)
    assert everyone["total"] == len(PEOPLE)

    uni = {u["full_name"] for u in _listed(ids, "uni_admin", limit=100)["users"]}
    assert uni == {"uni_admin", "uni_admin2", "cs_admin", "me_admin", "cs_fac", "cs_stu", "me_fac"}

    cs = {u["full_name"] for u in _listed(ids, "cs_admin", limit=100)["users"]}
    assert cs == {"cs_admin", "cs_fac", "cs_stu"}

    for key in ("cs_fac", "cs_stu", "newbie"):
        response = client.get("/api/v1/admin/users", headers=_auth(ids, key))
        assert response.status_code == 403, key


def test_list_items_carry_membership(ids):
    users = {u["full_name"]: u for u in _listed(ids, "super", limit=100)["users"]}
    cs_fac = users["cs_fac"]
    assert cs_fac["organization_id"] == ids["uni"]
    assert cs_fac["organization"] == "State University"
    assert cs_fac["department_id"] == ids["cs"]
    assert cs_fac["department"] == "Computer Science"
    assert "hashed_password" not in cs_fac


def test_list_search_filters_and_pagination(ids):
    assert {u["full_name"] for u in _listed(ids, "super", search="CS_")["users"]} == {
        "cs_admin",
        "cs_fac",
        "cs_stu",
    }
    assert _listed(ids, "super", search="law_fac@admin")["total"] == 1
    assert {u["full_name"] for u in _listed(ids, "super", role="org_admin")["users"]} == {
        "uni_admin",
        "uni_admin2",
        "other_admin",
    }
    assert _listed(ids, "super", organization_id=ids["other"])["total"] == 2
    assert {
        u["full_name"] for u in _listed(ids, "super", department_id=ids["me"])["users"]
    } == {"me_admin", "me_fac"}
    # Filters never widen an admin's scope.
    assert _listed(ids, "uni_admin", organization_id=ids["other"])["total"] == 0

    first = _listed(ids, "super", limit=4, page=1)
    second = _listed(ids, "super", limit=4, page=2)
    assert first["total"] == second["total"] == len(PEOPLE)
    assert len(first["users"]) == len(second["users"]) == 4
    assert not {u["id"] for u in first["users"]} & {u["id"] for u in second["users"]}

    bad = client.get("/api/v1/admin/users?role=wizard", headers=_auth(ids, "super"))
    assert bad.status_code == 422


# ── PATCH /admin/users/{id}: super_admin ─────────────────────────────


def test_super_admin_onboards_user(ids):
    response = _patch_user(
        ids,
        "super",
        "newbie",
        {"role": "faculty", "organization_id": ids["uni"], "department_id": ids["phys"]},
    )
    assert response.status_code == 200, response.json()
    body = response.json()
    assert (body["role"], body["organization_id"], body["department_id"]) == (
        "faculty",
        ids["uni"],
        ids["phys"],
    )
    assert (body["organization"], body["department"]) == ("State University", "Physics")
    stored = _user(ids["newbie"])
    # Legacy name columns are kept in sync.
    assert (stored.organization, stored.department) == ("State University", "Physics")


def test_super_admin_rules(ids):
    # Cannot change their own role.
    own = _patch_user(ids, "super", "super", {"role": "faculty"})
    assert own.status_code == 403
    assert "own role" in own.json()["detail"]
    # But may change their own membership.
    assert _patch_user(ids, "super", "super", {"organization_id": ids["uni"]}).status_code == 200

    # Can grant and then revoke super_admin (two exist at that point).
    assert _patch_user(ids, "super", "newbie", {"role": "super_admin"}).status_code == 200
    assert _patch_user(ids, "super", "newbie", {"role": "normal_user"}).status_code == 200

    # Department must belong to the user's organization.
    mismatch = _patch_user(ids, "super", "cs_fac", {"department_id": ids["law"]})
    assert mismatch.status_code == 422
    assert "does not belong" in mismatch.json()["detail"]
    assert _patch_user(ids, "super", "cs_fac", {"organization_id": 999999}).status_code == 422
    assert _patch_user(ids, "super", "cs_fac", {"department_id": 999999}).status_code == 422

    # Moving organization clears the old department...
    moved = _patch_user(ids, "super", "cs_fac", {"organization_id": ids["other"]})
    assert moved.status_code == 200
    assert (moved.json()["organization_id"], moved.json()["department_id"]) == (ids["other"], None)
    # ...or takes a department of the new organization in the same request.
    moved = _patch_user(
        ids, "super", "cs_stu", {"organization_id": ids["other"], "department_id": ids["law"]}
    )
    assert moved.status_code == 200
    assert moved.json()["department"] == "Law"
    # Clearing the organization clears everything.
    cleared = _patch_user(ids, "super", "me_fac", {"organization_id": None})
    assert cleared.status_code == 200
    assert (cleared.json()["organization_id"], cleared.json()["department_id"]) == (None, None)
    assert _user(ids["me_fac"]).department is None

    # Admin roles need the matching membership.
    assert _patch_user(ids, "super", "newbie", {"role": "org_admin"}).status_code == 422
    assert _patch_user(ids, "super", "newbie", {"role": "department_admin"}).status_code == 422
    assert (
        _patch_user(
            ids,
            "super",
            "newbie",
            {"role": "department_admin", "organization_id": ids["uni"], "department_id": ids["me"]},
        ).status_code
        == 200
    )


def test_last_super_admin_cannot_be_demoted(ids):
    # Unreachable through the API (a super_admin cannot change their own
    # role, and demoting another implies two exist), so check the service.
    acting = User(id=10_000, email="ghost@x", full_name="ghost", role="super_admin")
    with TestSession() as session:
        target = session.get(User, ids["super"])
        with pytest.raises(UserAdminError) as exc:
            apply_user_update(session, acting, target, {"role": "faculty"})
        assert exc.value.status_code == 422
        assert "last super admin" in exc.value.detail.lower()


# ── PATCH /admin/users/{id}: org_admin ───────────────────────────────


def test_org_admin_rules(ids):
    ok = _patch_user(ids, "uni_admin", "cs_fac", {"role": "department_admin"})
    assert ok.status_code == 200, ok.json()
    for role in ("faculty", "student", "approver", "normal_user"):
        assert _patch_user(ids, "uni_admin", "cs_stu", {"role": role}).status_code == 200

    for role in ("org_admin", "super_admin"):
        denied = _patch_user(ids, "uni_admin", "cs_stu", {"role": role})
        assert denied.status_code == 403, role
        assert role in denied.json()["detail"]

    # Peers and superiors are off limits; so is anyone outside the org.
    assert _patch_user(ids, "uni_admin", "uni_admin2", {"role": "faculty"}).status_code == 403
    assert _patch_user(ids, "uni_admin", "super", {"department_id": ids["cs"]}).status_code == 403
    outside = _patch_user(ids, "uni_admin", "law_fac", {"role": "student"})
    assert outside.status_code == 403
    assert "organization" in outside.json()["detail"]
    assert _patch_user(ids, "uni_admin", "newbie", {"role": "student"}).status_code == 403

    # Departments inside their organization only; never another organization.
    assert _patch_user(ids, "uni_admin", "me_fac", {"department_id": ids["phys"]}).status_code == 200
    assert _patch_user(ids, "uni_admin", "me_fac", {"department_id": ids["law"]}).status_code == 403
    assert _patch_user(ids, "uni_admin", "me_fac", {"department_id": None}).status_code == 200
    assert (
        _patch_user(ids, "uni_admin", "me_fac", {"organization_id": ids["other"]}).status_code
        == 403
    )
    assert _patch_user(ids, "uni_admin", "me_fac", {"organization_id": None}).status_code == 403
    # Re-sending the current organization is a no-op, not a move.
    assert (
        _patch_user(ids, "uni_admin", "me_fac", {"organization_id": ids["uni"]}).status_code
        == 200
    )

    # No self-escalation (or any self role change).
    assert _patch_user(ids, "uni_admin", "uni_admin", {"role": "super_admin"}).status_code == 403
    assert _patch_user(ids, "uni_admin", "uni_admin", {"role": "faculty"}).status_code == 403

    # A department admin needs a department.
    assert (
        _patch_user(ids, "uni_admin", "me_fac", {"role": "department_admin"}).status_code
        == 422
    )


# ── PATCH /admin/users/{id}: department_admin ────────────────────────


def test_department_admin_rules(ids):
    for role in ("student", "approver", "normal_user", "faculty"):
        assert _patch_user(ids, "cs_admin", "cs_fac", {"role": role}).status_code == 200
    for role in ("department_admin", "org_admin", "super_admin"):
        assert _patch_user(ids, "cs_admin", "cs_fac", {"role": role}).status_code == 403, role

    move = _patch_user(ids, "cs_admin", "cs_fac", {"department_id": ids["me"]})
    assert move.status_code == 403
    assert _patch_user(ids, "cs_admin", "cs_fac", {"department_id": None}).status_code == 403
    assert (
        _patch_user(ids, "cs_admin", "cs_fac", {"organization_id": ids["other"]}).status_code
        == 403
    )
    # Unchanged values are fine.
    assert (
        _patch_user(
            ids, "cs_admin", "cs_fac", {"organization_id": ids["uni"], "department_id": ids["cs"]}
        ).status_code
        == 200
    )

    other_dept = _patch_user(ids, "cs_admin", "me_fac", {"role": "student"})
    assert other_dept.status_code == 403
    assert "department" in other_dept.json()["detail"]
    assert _patch_user(ids, "cs_admin", "me_admin", {"role": "faculty"}).status_code == 403
    assert _patch_user(ids, "cs_admin", "cs_admin", {"role": "org_admin"}).status_code == 403


def test_non_admins_and_bad_payloads(ids):
    for actor in ("cs_fac", "cs_stu", "newbie"):
        assert _patch_user(ids, actor, "cs_stu", {"role": "faculty"}).status_code == 403
        assert _patch_user(ids, actor, actor, {"role": "super_admin"}).status_code == 403
    assert _patch_user(ids, "super", "cs_fac", {"role": "wizard"}).status_code == 422
    assert _patch_user(ids, "super", "cs_fac", {"role": None}).status_code == 422
    assert _patch_user(ids, "super", "cs_fac", {"email": "x@y.z"}).status_code == 422
    assert _patch_user(ids, "super", "cs_fac", {"is_active": False}).status_code == 422
    missing = client.patch(
        "/api/v1/admin/users/999999", json={"role": "faculty"}, headers=_auth(ids, "super")
    )
    assert missing.status_code == 404
    # The stored user is untouched by every rejected request.
    assert _user(ids["cs_stu"]).role == "student"


def test_cookie_requests_need_csrf_header(ids):
    cookie_client = TestClient(app)
    cookie_client.cookies.set(ACCESS_COOKIE_NAME, create_access_token(str(ids["super"])))
    url = f"/api/v1/admin/users/{ids['cs_fac']}"
    assert cookie_client.patch(url, json={"role": "student"}).status_code == 403
    ok = cookie_client.patch(
        url, json={"role": "student"}, headers={"X-Requested-With": "TemplateOS"}
    )
    assert ok.status_code == 200


# ── /auth/me ─────────────────────────────────────────────────────────


def test_get_me_includes_membership(ids):
    body = client.get("/api/v1/auth/me", headers=_auth(ids, "cs_fac")).json()
    assert body["organization_id"] == ids["uni"]
    assert body["organization"] == "State University"
    assert body["department_id"] == ids["cs"]
    assert body["department"] == "Computer Science"


def test_patch_me_updates_safe_fields(ids):
    response = client.patch(
        "/api/v1/auth/me",
        json={"full_name": "  Ada Lovelace ", "phone": " +91 98765 43210 ", "job_title": "Professor"},
        headers=_auth(ids, "cs_fac"),
    )
    assert response.status_code == 200, response.json()
    body = response.json()
    assert (body["full_name"], body["phone"], body["job_title"]) == (
        "Ada Lovelace",
        "+91 98765 43210",
        "Professor",
    )
    # Blank optional fields clear them; omitted fields stay.
    cleared = client.patch(
        "/api/v1/auth/me", json={"phone": "  "}, headers=_auth(ids, "cs_fac")
    ).json()
    assert cleared["phone"] is None
    assert cleared["job_title"] == "Professor"


@pytest.mark.parametrize(
    "body",
    [
        {"role": "super_admin"},
        {"organization_id": 1},
        {"department_id": 1},
        {"organization": "Hacker U"},
        {"department": "Root"},
        {"full_name": "Fine Name", "role": "org_admin"},
        {"email": "new@x.y"},
        {"full_name": None},
        {"full_name": " x "},
        {"phone": "9" * 51},
    ],
)
def test_patch_me_rejects_privileged_or_invalid_fields(ids, body):
    response = client.patch("/api/v1/auth/me", json=body, headers=_auth(ids, "cs_stu"))
    assert response.status_code == 422
    stored = _user(ids["cs_stu"])
    assert (stored.role, stored.organization_id, stored.department_id, stored.full_name) == (
        "student",
        ids["uni"],
        ids["cs"],
        "cs_stu",
    )


def test_patch_me_requires_auth(ids):
    assert client.patch("/api/v1/auth/me", json={"full_name": "Nobody"}).status_code == 401


# ── organizations ────────────────────────────────────────────────────


def test_list_organizations_for_any_user(ids):
    response = client.get("/api/v1/admin/organizations", headers=_auth(ids, "newbie"))
    assert response.status_code == 200
    by_name = {org["name"]: org for org in response.json()}
    assert list(by_name) == ["Empty Institute", "Other College", "State University"]
    assert by_name["State University"]["department_count"] == 3
    assert by_name["State University"]["user_count"] == 7
    assert client.get("/api/v1/admin/organizations").status_code == 401


def test_organization_writes_are_super_admin_only(ids):
    for actor in ("uni_admin", "cs_admin", "cs_fac"):
        assert (
            client.post(
                "/api/v1/admin/organizations", json={"name": "New U"}, headers=_auth(ids, actor)
            ).status_code
            == 403
        )
        assert (
            client.patch(
                f"/api/v1/admin/organizations/{ids['uni']}",
                json={"name": "Renamed"},
                headers=_auth(ids, actor),
            ).status_code
            == 403
        )
        assert (
            client.delete(
                f"/api/v1/admin/organizations/{ids['empty']}", headers=_auth(ids, actor)
            ).status_code
            == 403
        )


def test_organization_create_rename_delete(ids):
    headers = _auth(ids, "super")
    created = client.post(
        "/api/v1/admin/organizations", json={"name": "  New   University "}, headers=headers
    )
    assert created.status_code == 201
    assert created.json()["name"] == "New University"

    dup = client.post(
        "/api/v1/admin/organizations", json={"name": "state UNIVERSITY"}, headers=headers
    )
    assert dup.status_code == 409
    assert (
        client.post("/api/v1/admin/organizations", json={"name": "   "}, headers=headers).status_code
        == 422
    )

    # Rename propagates to the legacy name copies.
    with TestSession() as session:
        session.add(
            Template(
                name="t",
                category="notice",
                visibility="organization",
                uploaded_by=ids["uni_admin"],
                scope_organization_id=ids["uni"],
                scope_organization="State University",
            )
        )
        session.commit()
    renamed = client.patch(
        f"/api/v1/admin/organizations/{ids['uni']}",
        json={"name": "State University of Tech"},
        headers=headers,
    )
    assert renamed.status_code == 200
    assert _user(ids["cs_fac"]).organization == "State University of Tech"
    with TestSession() as session:
        assert session.scalar(select(Template.scope_organization)) == "State University of Tech"
    # Renaming to a different case of itself is allowed; onto another is not.
    assert (
        client.patch(
            f"/api/v1/admin/organizations/{ids['uni']}",
            json={"name": "STATE UNIVERSITY OF TECH"},
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/admin/organizations/{ids['uni']}",
            json={"name": "other college"},
            headers=headers,
        ).status_code
        == 409
    )
    assert (
        client.patch(
            "/api/v1/admin/organizations/999999", json={"name": "x"}, headers=headers
        ).status_code
        == 404
    )

    # In use -> 409; unused (with an unused department) -> deleted with it.
    in_use = client.delete(f"/api/v1/admin/organizations/{ids['other']}", headers=headers)
    assert in_use.status_code == 409
    assert "in use" in in_use.json()["detail"]
    assert (
        client.delete(f"/api/v1/admin/organizations/{ids['empty']}", headers=headers).status_code
        == 204
    )
    with TestSession() as session:
        assert session.get(Department, ids["unused"]) is None
    assert (
        client.delete(f"/api/v1/admin/organizations/{ids['empty']}", headers=headers).status_code
        == 404
    )


def test_organization_used_only_by_a_template_is_in_use(ids):
    with TestSession() as session:
        session.add(
            Template(
                name="t",
                category="notice",
                visibility="department",
                uploaded_by=ids["super"],
                scope_organization_id=ids["empty"],
                scope_department_id=ids["unused"],
            )
        )
        session.commit()
    headers = _auth(ids, "super")
    response = client.delete(f"/api/v1/admin/organizations/{ids['empty']}", headers=headers)
    assert response.status_code == 409
    assert "template" in response.json()["detail"]
    assert (
        client.delete(f"/api/v1/admin/departments/{ids['unused']}", headers=headers).status_code
        == 409
    )


# ── departments ──────────────────────────────────────────────────────


def _dept_names(response):
    assert response.status_code == 200, response.json()
    return {d["name"] for d in response.json()}


def test_list_departments_scoping(ids):
    url = "/api/v1/admin/departments"
    assert _dept_names(client.get(url, headers=_auth(ids, "super"))) == {
        name for _, name in DEPTS.values()
    }
    assert _dept_names(
        client.get(url, params={"organization_id": ids["other"]}, headers=_auth(ids, "super"))
    ) == {"Law"}
    uni = {"Computer Science", "Mechanical", "Physics"}
    assert _dept_names(client.get(url, headers=_auth(ids, "uni_admin"))) == uni
    assert _dept_names(client.get(url, headers=_auth(ids, "cs_fac"))) == uni
    assert (
        client.get(
            url, params={"organization_id": ids["other"]}, headers=_auth(ids, "uni_admin")
        ).status_code
        == 403
    )
    assert _dept_names(client.get(url, headers=_auth(ids, "newbie"))) == set()
    counts = {d["name"]: d["user_count"] for d in client.get(url, headers=_auth(ids, "uni_admin")).json()}
    assert counts == {"Computer Science": 3, "Mechanical": 2, "Physics": 0}


def test_department_create_permissions(ids):
    url = "/api/v1/admin/departments"
    own = client.post(url, json={"name": "Chemistry"}, headers=_auth(ids, "uni_admin"))
    assert own.status_code == 201, own.json()
    assert own.json()["organization_id"] == ids["uni"]
    assert (
        client.post(
            url, json={"name": "Civil", "organization_id": ids["uni"]}, headers=_auth(ids, "uni_admin")
        ).status_code
        == 201
    )
    elsewhere = client.post(
        url, json={"name": "Chemistry", "organization_id": ids["other"]}, headers=_auth(ids, "uni_admin")
    )
    assert elsewhere.status_code == 403
    for actor in ("cs_admin", "cs_fac"):
        assert (
            client.post(url, json={"name": "Biology", "organization_id": ids["uni"]}, headers=_auth(ids, actor)).status_code
            == 403
        )
        assert client.post(url, json={"name": "Biology"}, headers=_auth(ids, actor)).status_code == 403

    dup = client.post(url, json={"name": " computer  SCIENCE"}, headers=_auth(ids, "uni_admin"))
    assert dup.status_code == 409
    # Same name in another organization is a different department.
    assert (
        client.post(
            url, json={"name": "Computer Science", "organization_id": ids["other"]}, headers=_auth(ids, "super")
        ).status_code
        == 201
    )
    assert client.post(url, json={"name": "X"}, headers=_auth(ids, "super")).status_code == 422
    assert (
        client.post(url, json={"name": "X", "organization_id": 999999}, headers=_auth(ids, "super")).status_code
        == 422
    )


def test_department_rename_and_delete(ids):
    url = "/api/v1/admin/departments"
    renamed = client.patch(
        f"{url}/{ids['cs']}", json={"name": "Computer Science & Engineering"}, headers=_auth(ids, "uni_admin")
    )
    assert renamed.status_code == 200
    assert _user(ids["cs_fac"]).department == "Computer Science & Engineering"
    assert (
        client.patch(f"{url}/{ids['me']}", json={"name": "physics"}, headers=_auth(ids, "uni_admin")).status_code
        == 409
    )
    assert (
        client.patch(f"{url}/{ids['law']}", json={"name": "Laws"}, headers=_auth(ids, "uni_admin")).status_code
        == 403
    )
    assert (
        client.patch(f"{url}/{ids['cs']}", json={"name": "CS"}, headers=_auth(ids, "cs_admin")).status_code
        == 403
    )
    assert client.patch(f"{url}/999999", json={"name": "x"}, headers=_auth(ids, "super")).status_code == 404

    in_use = client.delete(f"{url}/{ids['cs']}", headers=_auth(ids, "uni_admin"))
    assert in_use.status_code == 409
    assert "3 users" in in_use.json()["detail"]
    assert client.delete(f"{url}/{ids['law']}", headers=_auth(ids, "uni_admin")).status_code == 403
    assert client.delete(f"{url}/{ids['phys']}", headers=_auth(ids, "cs_admin")).status_code == 403
    assert client.delete(f"{url}/{ids['phys']}", headers=_auth(ids, "uni_admin")).status_code == 204
    assert client.delete(f"{url}/{ids['phys']}", headers=_auth(ids, "uni_admin")).status_code == 404
