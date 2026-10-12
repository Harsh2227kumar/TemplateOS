"""
Organization / department scoped templates with role-restricted audiences.

- View rule vs library SQL filter parity across a users x templates matrix.
- can_manage.
- Publish rules (resolve_publish_access) and their HTTP mapping.
- POST /templates/upload with scope fields, PATCH /templates/{id}/access,
  GET /templates/access-options, and can_manage-gated modifying endpoints.
"""

import io
import itertools
import json
import os

import pytest
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

from app.core.security import create_access_token
from app.crud.template_crud import get_library_templates
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.template import Template
from app.models.user import User
from app.services.template_access import (
    PublishRuleError,
    can_manage,
    resolve_publish_access,
    user_can_view_template,
)

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

UNI = "State University"
OTHER = "Other College"

# key: (role, organization, department)
USERS = {
    "super": ("super_admin", None, None),
    "uni_org_admin": ("org_admin", UNI, None),
    "other_org_admin": ("org_admin", OTHER, None),
    "cs_dept_admin": ("department_admin", UNI, "Computer Science"),
    "me_dept_admin": ("department_admin", UNI, "Mechanical"),
    "cs_faculty": ("faculty", UNI, "Computer Science"),
    # Same department text, different case / padding: must still match.
    "cs_student": ("student", "  state university ", "computer science "),
    "cs_staff": ("normal_user", UNI, "Computer Science"),
    "me_faculty": ("faculty", UNI, "Mechanical"),
    "other_cs_faculty": ("faculty", OTHER, "Computer Science"),
    "no_org_student": ("student", None, None),
    "approver": ("approver", UNI, None),
}


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    old = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    if old is not None:
        app.dependency_overrides[get_db] = old
    else:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="module")
def users(setup_db) -> dict[str, int]:
    ids = {}
    with TestSession() as session:
        for key, (role, org, dept) in USERS.items():
            user = User(
                email=f"{key}@access.test",
                full_name=key,
                role=role,
                organization=org,
                department=dept,
            )
            session.add(user)
            session.flush()
            ids[key] = user.id
        session.commit()
    return ids


def _token(users: dict[str, int], key: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(users[key]))}"}


# (name, owner key, visibility, scope_org, scope_dept, allowed_roles list)
TEMPLATE_SPECS = [
    ("private", "cs_faculty", "private", None, None, None),
    ("public", "cs_faculty", "public", None, None, None),
    ("public_faculty_only", "uni_org_admin", "public", None, None, ["faculty"]),
    ("uni_letterhead", "uni_org_admin", "organization", UNI, None, None),
    ("uni_letterhead_ci", "super", "organization", " state UNIVERSITY", None, None),
    ("uni_staff_only", "uni_org_admin", "organization", UNI, None, ["faculty", "normal_user"]),
    ("other_letterhead", "other_org_admin", "organization", OTHER, None, None),
    ("cs_dept", "cs_dept_admin", "department", UNI, "Computer Science", None),
    (
        "cs_dept_no_students",
        "cs_dept_admin",
        "department",
        UNI,
        "Computer Science",
        ["faculty", "normal_user", "department_admin"],
    ),
    ("cs_dept_any_org", "super", "department", None, "Computer Science", None),
    ("me_dept", "me_dept_admin", "department", UNI, "Mechanical", None),
    ("group_faculty", "cs_faculty", "group", None, None, None),
    ("legacy_org_unscoped", "cs_faculty", "organization", None, None, None),
    ("malformed_roles", "uni_org_admin", "public", None, None, "not-json"),
    ("empty_roles", "uni_org_admin", "organization", UNI, None, "[]"),
]


@pytest.fixture(scope="module")
def templates(users) -> dict[str, int]:
    ids = {}
    with TestSession() as session:
        for name, owner, visibility, org, dept, roles in TEMPLATE_SPECS:
            if isinstance(roles, list):
                roles = json.dumps(roles)
            template = Template(
                name=name,
                category="notice",
                visibility=visibility,
                uploaded_by=users[owner],
                scope_organization=org,
                scope_department=dept,
                allowed_roles=roles,
            )
            session.add(template)
            session.flush()
            ids[name] = template.id
        session.commit()
    return ids


# ── parity: Python view rule == library SQL filter ───────────────────


def test_view_rule_matches_library_filter_for_every_user(users, templates):
    with TestSession() as session:
        all_templates = session.query(Template).all()
        assert len(all_templates) == len(TEMPLATE_SPECS)
        for key in USERS:
            user = session.get(User, users[key])
            expected = {t.name for t in all_templates if user_can_view_template(user, t)}
            listed, total = get_library_templates(session, user.id, limit=100)
            assert {t.name for t in listed} == expected, key
            assert total == len(expected), key


EXPECTED_VISIBLE = {
    "cs_student": {
        "public",
        "uni_letterhead",
        "uni_letterhead_ci",
        "cs_dept",
        "cs_dept_any_org",
        "empty_roles",
    },
    "cs_faculty": {
        "private",
        "public",
        "public_faculty_only",
        "uni_letterhead",
        "uni_letterhead_ci",
        "uni_staff_only",
        "cs_dept",
        "cs_dept_no_students",
        "cs_dept_any_org",
        "group_faculty",
        "legacy_org_unscoped",
        "empty_roles",
    },
    "other_cs_faculty": {
        "public",
        "public_faculty_only",
        "other_letterhead",
        "cs_dept_any_org",
        "group_faculty",
    },
    # Scope manager: sees restricted org + all dept templates of the org.
    "uni_org_admin": {
        "public",
        "public_faculty_only",
        "uni_letterhead",
        "uni_letterhead_ci",
        "uni_staff_only",
        "cs_dept",
        "cs_dept_no_students",
        "me_dept",
        "malformed_roles",
        "empty_roles",
    },
    # Department manager sees its department even when restricted; not other depts.
    "me_dept_admin": {
        "public",
        "uni_letterhead",
        "uni_letterhead_ci",
        "me_dept",
        "empty_roles",
    },
    "no_org_student": {"public"},
}


@pytest.mark.parametrize("key", sorted(EXPECTED_VISIBLE))
def test_view_rule_expected_sets(users, templates, key):
    with TestSession() as session:
        user = session.get(User, users[key])
        visible = {
            t.name for t in session.query(Template).all() if user_can_view_template(user, t)
        }
    assert visible == EXPECTED_VISIBLE[key]


def test_super_admin_sees_everything(users, templates):
    with TestSession() as session:
        listed, total = get_library_templates(session, users["super"], limit=100)
    assert total == len(TEMPLATE_SPECS)


# ── can_manage ───────────────────────────────────────────────────────

EXPECTED_MANAGE = {
    "super": {name for name, *_ in TEMPLATE_SPECS},
    "uni_org_admin": {
        "public_faculty_only",
        "uni_letterhead",
        "uni_letterhead_ci",
        "uni_staff_only",
        "cs_dept",
        "cs_dept_no_students",
        "me_dept",
        "malformed_roles",
        "empty_roles",
    },
    "other_org_admin": {"other_letterhead"},
    "cs_dept_admin": {"cs_dept", "cs_dept_no_students", "cs_dept_any_org"},
    "me_dept_admin": {"me_dept"},
    "cs_faculty": {"private", "public", "group_faculty", "legacy_org_unscoped"},
    "cs_student": set(),
}


@pytest.mark.parametrize("key", sorted(EXPECTED_MANAGE))
def test_can_manage(users, templates, key):
    with TestSession() as session:
        user = session.get(User, users[key])
        managed = {t.name for t in session.query(Template).all() if can_manage(user, t)}
    assert managed == EXPECTED_MANAGE[key]


def test_can_manage_implies_can_view(users, templates):
    with TestSession() as session:
        all_templates = session.query(Template).all()
        for key in USERS:
            user = session.get(User, users[key])
            for template in all_templates:
                if can_manage(user, template):
                    assert user_can_view_template(user, template), (key, template.name)


# ── publish rules ────────────────────────────────────────────────────


def _user(role, org=UNI, dept=None):
    return User(email="x@x", full_name="x", role=role, organization=org, department=dept)


@pytest.mark.parametrize(
    "role", ["faculty", "student", "approver", "normal_user"]
)
@pytest.mark.parametrize("visibility", ["organization", "department"])
def test_non_admins_cannot_publish_scoped(role, visibility):
    with pytest.raises(PublishRuleError) as exc:
        resolve_publish_access(_user(role, dept="CS"), visibility, UNI, "CS", None)
    assert exc.value.status_code == 403


def test_org_admin_scope_forced_to_own_org():
    resolved = resolve_publish_access(_user("org_admin"), "organization", None, None, None)
    assert resolved.scope_organization == UNI
    assert resolved.scope_department is None
    # Same org in a different case is accepted (and normalized to the profile).
    resolved = resolve_publish_access(
        _user("org_admin"), "organization", " state university", None, None
    )
    assert resolved.scope_organization == UNI
    with pytest.raises(PublishRuleError) as exc:
        resolve_publish_access(_user("org_admin"), "organization", OTHER, None, None)
    assert exc.value.status_code == 403


def test_org_admin_department_requires_department():
    with pytest.raises(PublishRuleError) as exc:
        resolve_publish_access(_user("org_admin"), "department", None, None, None)
    assert exc.value.status_code == 422
    resolved = resolve_publish_access(
        _user("org_admin"), "department", None, " Physics ", None
    )
    assert (resolved.scope_organization, resolved.scope_department) == (UNI, "Physics")


def test_department_admin_rules():
    admin = _user("department_admin", dept="Computer Science")
    with pytest.raises(PublishRuleError) as exc:
        resolve_publish_access(admin, "organization", None, None, None)
    assert exc.value.status_code == 403
    resolved = resolve_publish_access(admin, "department", None, None, None)
    assert (resolved.scope_organization, resolved.scope_department) == (
        UNI,
        "Computer Science",
    )
    with pytest.raises(PublishRuleError):
        resolve_publish_access(admin, "department", None, "Mechanical", None)
    with pytest.raises(PublishRuleError) as exc:
        resolve_publish_access(
            _user("department_admin", dept=None), "department", None, None, None
        )
    assert exc.value.status_code == 422


def test_super_admin_must_name_scope():
    admin = _user("super_admin", org=None)
    with pytest.raises(PublishRuleError) as exc:
        resolve_publish_access(admin, "organization", None, None, None)
    assert exc.value.status_code == 422
    with pytest.raises(PublishRuleError) as exc:
        resolve_publish_access(admin, "department", OTHER, None, None)
    assert exc.value.status_code == 422
    resolved = resolve_publish_access(admin, "department", OTHER, "Law", None)
    assert (resolved.scope_organization, resolved.scope_department) == (OTHER, "Law")


def test_allowed_roles_validation():
    admin = _user("org_admin")
    resolved = resolve_publish_access(
        admin, "organization", None, None, ["student", "faculty", "faculty"]
    )
    assert json.loads(resolved.allowed_roles) == ["faculty", "student"]
    assert resolve_publish_access(admin, "organization", None, None, []).allowed_roles is None
    for bad in (["super_admin"], ["wizard"]):
        with pytest.raises(PublishRuleError) as exc:
            resolve_publish_access(admin, "organization", None, None, bad)
        assert exc.value.status_code == 422


def test_unscoped_visibilities_clear_scope():
    resolved = resolve_publish_access(_user("faculty"), "public", UNI, "CS", ["faculty"])
    assert resolved.scope_organization is None and resolved.scope_department is None
    assert json.loads(resolved.allowed_roles) == ["faculty"]
    private = resolve_publish_access(_user("faculty"), "private", None, None, ["faculty"])
    assert private.allowed_roles is None


# ── HTTP: upload / access / access-options ───────────────────────────


def _docx() -> bytes:
    document = Document()
    document.add_paragraph("Dear {{recipient_name}},")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _upload(headers, **data):
    payload = {"name": "Scoped", "category": "notice", "visibility": "private", **data}
    return client.post(
        "/api/v1/templates/upload",
        files={
            "file": (
                "scoped.docx",
                io.BytesIO(_docx()),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data=payload,
        headers=headers,
    )


def test_upload_department_template_by_department_admin(users):
    response = _upload(
        _token(users, "cs_dept_admin"),
        visibility="department",
        allowed_roles="faculty, normal_user",
    )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["scope_organization"] == UNI
    assert body["scope_department"] == "Computer Science"
    assert body["allowed_roles"] == ["faculty", "normal_user"]
    assert body["can_manage"] is True

    # Faculty in the department can open it; the student cannot.
    template_id = body["id"]
    faculty = client.get(f"/api/v1/templates/{template_id}", headers=_token(users, "cs_faculty"))
    assert faculty.status_code == 200
    assert faculty.json()["can_manage"] is False
    student = client.get(f"/api/v1/templates/{template_id}", headers=_token(users, "cs_student"))
    assert student.status_code == 403
    # ...and it is not in the student's library.
    library = client.get("/api/v1/templates/library", headers=_token(users, "cs_student"))
    assert template_id not in {t["id"] for t in library.json()["templates"]}


def test_upload_rejections(users):
    assert _upload(_token(users, "cs_faculty"), visibility="organization").status_code == 403
    response = _upload(_token(users, "cs_dept_admin"), visibility="organization")
    assert response.status_code == 403
    assert "department" in response.json()["detail"].lower()
    assert _upload(_token(users, "super"), visibility="organization").status_code == 422
    assert (
        _upload(_token(users, "uni_org_admin"), visibility="organization", allowed_roles="god")
        .status_code
        == 422
    )


def test_upload_super_admin_scoped(users):
    response = _upload(
        _token(users, "super"),
        visibility="organization",
        scope_organization=OTHER,
        allowed_roles="",
    )
    assert response.status_code == 201
    assert response.json()["scope_organization"] == OTHER
    assert response.json()["allowed_roles"] is None


def test_library_items_carry_audience(users):
    response = client.get("/api/v1/templates/library?limit=100", headers=_token(users, "uni_org_admin"))
    assert response.status_code == 200
    items = {t["name"]: t for t in response.json()["templates"]}
    staff_only = items["uni_staff_only"]
    assert staff_only["scope_organization"] == UNI
    assert staff_only["allowed_roles"] == ["faculty", "normal_user"]
    assert staff_only["can_manage"] is True
    assert items["public"]["can_manage"] is False


def test_patch_access(users, templates):
    template_id = templates["cs_dept"]
    url = f"/api/v1/templates/{template_id}/access"

    # Viewers who cannot manage get 403.
    denied = client.patch(url, json={"visibility": "private"}, headers=_token(users, "cs_faculty"))
    assert denied.status_code == 403

    # Department admin restricts it to faculty.
    response = client.patch(
        url,
        json={"visibility": "department", "allowed_roles": ["faculty"]},
        headers=_token(users, "cs_dept_admin"),
    )
    assert response.status_code == 200, response.json()
    assert response.json()["allowed_roles"] == ["faculty"]
    assert response.json()["scope_department"] == "Computer Science"
    assert client.get(f"/api/v1/templates/{template_id}", headers=_token(users, "cs_staff")).status_code == 403

    # Department admin cannot widen to the organization.
    widen = client.patch(url, json={"visibility": "organization"}, headers=_token(users, "cs_dept_admin"))
    assert widen.status_code == 403

    # The org admin (scope manager) can, and clearing roles reopens it.
    response = client.patch(
        url,
        json={"visibility": "organization", "allowed_roles": []},
        headers=_token(users, "uni_org_admin"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["visibility"] == "organization"
    assert body["scope_organization"] == UNI
    assert body["scope_department"] is None
    assert body["allowed_roles"] is None
    assert client.get(f"/api/v1/templates/{template_id}", headers=_token(users, "cs_staff")).status_code == 200

    invalid = client.patch(url, json={"visibility": "everyone"}, headers=_token(users, "super"))
    assert invalid.status_code == 422
    missing = client.patch("/api/v1/templates/999999/access", json={"visibility": "private"}, headers=_token(users, "super"))
    assert missing.status_code == 404


def test_access_options(users):
    response = client.get("/api/v1/templates/access-options", headers=_token(users, "super"))
    assert response.status_code == 200
    body = response.json()
    role_values = [role["value"] for role in body["roles"]]
    assert "super_admin" not in role_values
    assert {"faculty", "student", "normal_user"} <= set(role_values)
    assert all(role["label"] for role in body["roles"])
    # Case/padding variants collapse to one entry.
    assert sorted(o.lower() for o in body["organizations"]) == sorted(
        {UNI.lower(), OTHER.lower()}
    )
    pairs = {(d["organization"].lower(), d["department"].lower()) for d in body["departments"]}
    assert (UNI.lower(), "computer science") in pairs
    assert (OTHER.lower(), "computer science") in pairs
    assert len(pairs) == len(body["departments"])
    assert body["can_publish"] == {"organization": True, "department": True}
    assert body["defaults"] == {"organization": None, "department": None}

    dept_admin = client.get(
        "/api/v1/templates/access-options", headers=_token(users, "cs_dept_admin")
    ).json()
    assert dept_admin["can_publish"] == {"organization": False, "department": True}
    assert dept_admin["defaults"] == {"organization": UNI, "department": "Computer Science"}
    assert [o.lower() for o in dept_admin["organizations"]] == [UNI.lower()]
    assert all(d["organization"].lower() == UNI.lower() for d in dept_admin["departments"])

    faculty = client.get(
        "/api/v1/templates/access-options", headers=_token(users, "cs_faculty")
    ).json()
    assert faculty["can_publish"] == {"organization": False, "department": False}


def test_access_options_route_not_shadowed_by_template_id(users):
    response = client.get("/api/v1/templates/access-options", headers=_token(users, "cs_student"))
    assert response.status_code == 200


def test_scope_manager_can_use_modifying_endpoints(users, templates):
    template_id = templates["me_dept"]
    field = {"field_name": "dean_name", "field_label": "Dean", "field_type": "text"}
    # The org admin manages the Mechanical department template.
    created = client.post(
        f"/api/v1/templates/{template_id}/fields",
        json=field,
        headers=_token(users, "uni_org_admin"),
    )
    assert created.status_code == 201, created.json()
    # A faculty member of that department can view but not modify.
    assert (
        client.get(f"/api/v1/templates/{template_id}/fields", headers=_token(users, "me_faculty")).status_code
        == 200
    )
    denied = client.post(
        f"/api/v1/templates/{template_id}/fields",
        json={**field, "field_name": "other"},
        headers=_token(users, "me_faculty"),
    )
    assert denied.status_code == 403
    # Another department's admin cannot either.
    assert (
        client.post(
            f"/api/v1/templates/{template_id}/detect-placeholders",
            headers=_token(users, "cs_dept_admin"),
        ).status_code
        == 403
    )


def test_delete_stays_super_admin_only(users, templates):
    response = client.delete(
        f"/api/v1/templates/{templates['other_letterhead']}",
        headers=_token(users, "other_org_admin"),
    )
    assert response.status_code == 403


def test_matrix_is_meaningful():
    # Guard: the parity matrix exercises every visibility and role restriction.
    visibilities = {spec[2] for spec in TEMPLATE_SPECS}
    assert visibilities == {"private", "public", "organization", "department", "group"}
    assert any(isinstance(spec[5], list) for spec in TEMPLATE_SPECS)
    assert len(list(itertools.product(USERS, TEMPLATE_SPECS))) >= 150
