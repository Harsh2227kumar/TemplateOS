"""
API tests for the V1.4 Phase 2 document endpoints (Member 2).

Coverage:
- Full flow: POST /documents/create -> PUT /{id}/values -> GET /documents ->
  GET /{id} -> GET /{id}/values; auto-generated name.
- 404 for unknown template / document; 403 when another user reads or saves.
- 422 {field_name, error} detail for required, email, min/max (text length,
  number value, list item count), number (incl. nan/inf), unknown field,
  duplicate field in payload, empty required list, malformed list value.
- Malformed validation_rule ("min:abc") is ignored with a logged warning.
- Saving values bumps documents.updated_at (and the list ordering).
"""

import logging
import os
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault(
    "JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests"
)

from app.crud.template_field_crud import create_field
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.document import Document
from app.models.template import Template
from app.models.user import User
from app.schemas.template_field import TemplateFieldCreate

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

OWNER_EMAIL = "doc_api_owner@example.com"
STRANGER_EMAIL = "doc_api_stranger@example.com"


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


def _signup_and_login(email: str, full_name: str) -> str:
    client.post(
        "/api/v1/auth/signup",
        json={"full_name": full_name, "email": email, "password": "strong-password"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "strong-password"},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


@pytest.fixture(scope="module")
def owner_token(setup_db):
    return _signup_and_login(OWNER_EMAIL, "Doc API Owner")


@pytest.fixture(scope="module")
def stranger_token(setup_db):
    return _signup_and_login(STRANGER_EMAIL, "Doc API Stranger")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_template(name: str, visibility: str = "public") -> int:
    with TestSession() as session:
        owner = session.execute(
            select(User).where(User.email == OWNER_EMAIL)
        ).scalar_one()
        template = Template(
            name=name,
            category="mom",
            visibility=visibility,
            uploaded_by=owner.id,
            status="field_configured",
        )
        session.add(template)
        session.commit()
        session.refresh(template)
        return template.id


@pytest.fixture(scope="module")
def template_id(owner_token):
    """Public template with one field per validation scenario."""
    tid = _make_template("Doc API Template")
    specs = [
        ("title", {"field_type": "text", "is_required": True}),
        ("contact", {"field_type": "text", "validation_rule": "email"}),
        ("summary", {"field_type": "text", "validation_rule": "min:3|max:10"}),
        ("count", {"field_type": "number", "validation_rule": "min:1|max:100"}),
        ("ratio", {"field_type": "number"}),
        (
            "items",
            {"field_type": "list", "is_required": True, "validation_rule": "min:2|max:3"},
        ),
        ("tags", {"field_type": "list"}),
        ("notes", {"field_type": "text", "validation_rule": "min:abc"}),
    ]
    with TestSession() as session:
        for name, overrides in specs:
            overrides.setdefault("is_required", False)
            create_field(session, tid, TemplateFieldCreate(field_name=name, **overrides))
    return tid


def _create_doc(token: str, template_id: int, name: str | None = "My Draft") -> dict:
    body = {"template_id": template_id}
    if name is not None:
        body["name"] = name
    response = client.post("/api/v1/documents/create", headers=_auth(token), json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _put_values(token: str, document_id: int, values: list[dict]):
    return client.put(
        f"/api/v1/documents/{document_id}/values",
        headers=_auth(token),
        json={"values": values},
    )


VALID_VALUES = [
    {"field_name": "title", "value": "Weekly sync"},
    {"field_name": "contact", "value": "a@example.com"},
    {"field_name": "summary", "value": "short"},
    {"field_name": "count", "value": "42"},
    {"field_name": "items", "value": '["one", "two"]'},
]


# ── Full flow ─────────────────────────────────────────────────────


def test_full_flow(owner_token, template_id):
    doc = _create_doc(owner_token, template_id, name="Flow Draft")
    assert doc["name"] == "Flow Draft"
    assert doc["status"] == "draft"
    assert doc["values"] == []

    saved = _put_values(owner_token, doc["id"], VALID_VALUES)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["document_id"] == doc["id"]
    assert {v["field_name"]: v["value"] for v in body["values"]} == {
        v["field_name"]: v["value"] for v in VALID_VALUES
    }

    # Upsert: second save updates the existing row instead of inserting.
    resaved = _put_values(
        owner_token, doc["id"], [{"field_name": "title", "value": "Renamed"}]
    )
    assert resaved.status_code == 200, resaved.text

    listed = client.get("/api/v1/documents", headers=_auth(owner_token))
    assert listed.status_code == 200, listed.text
    item = next(d for d in listed.json() if d["id"] == doc["id"])
    assert item["template_name"] == "Doc API Template"
    assert "values" not in item

    one = client.get(f"/api/v1/documents/{doc['id']}", headers=_auth(owner_token))
    assert one.status_code == 200, one.text
    one_values = {v["field_name"]: v["value"] for v in one.json()["values"]}
    assert one_values["title"] == "Renamed"
    assert len(one_values) == len(VALID_VALUES)

    only = client.get(
        f"/api/v1/documents/{doc['id']}/values", headers=_auth(owner_token)
    )
    assert only.status_code == 200, only.text
    assert only.json()["document_id"] == doc["id"]
    assert {v["field_name"] for v in only.json()["values"]} == {
        v["field_name"] for v in VALID_VALUES
    }


def test_create_auto_generates_name(owner_token, template_id):
    doc = _create_doc(owner_token, template_id, name=None)
    assert doc["name"].startswith("Doc API Template Draft - ")


# ── 404 / 403 ─────────────────────────────────────────────────────


def test_create_unknown_template_404(owner_token):
    response = client.post(
        "/api/v1/documents/create",
        headers=_auth(owner_token),
        json={"template_id": 999999},
    )
    assert response.status_code == 404


def test_unknown_document_404(owner_token):
    assert (
        client.get("/api/v1/documents/999999", headers=_auth(owner_token)).status_code
        == 404
    )
    assert (
        client.get(
            "/api/v1/documents/999999/values", headers=_auth(owner_token)
        ).status_code
        == 404
    )
    assert _put_values(owner_token, 999999, VALID_VALUES).status_code == 404


def test_create_from_private_template_of_other_user_403(stranger_token, owner_token):
    private_id = _make_template("Doc API Private", visibility="private")
    response = client.post(
        "/api/v1/documents/create",
        headers=_auth(stranger_token),
        json={"template_id": private_id},
    )
    assert response.status_code == 403


def test_other_user_cannot_read_or_save_document(
    owner_token, stranger_token, template_id
):
    doc = _create_doc(owner_token, template_id)
    doc_id = doc["id"]

    assert (
        client.get(f"/api/v1/documents/{doc_id}", headers=_auth(stranger_token)).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/documents/{doc_id}/values", headers=_auth(stranger_token)
        ).status_code
        == 403
    )
    assert _put_values(stranger_token, doc_id, VALID_VALUES).status_code == 403

    listed = client.get("/api/v1/documents", headers=_auth(stranger_token))
    assert listed.status_code == 200
    assert doc_id not in {d["id"] for d in listed.json()}


# ── 422 validation ────────────────────────────────────────────────


def _assert_field_error(response, field_name: str, contains: str | None = None):
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    for err in detail:
        assert set(err) == {"field_name", "error"}
    matches = [e for e in detail if e["field_name"] == field_name]
    assert matches, detail
    if contains is not None:
        assert any(contains in e["error"] for e in matches), matches


@pytest.mark.parametrize(
    "field_name,value,contains",
    [
        ("title", "   ", "required"),
        ("contact", "not-an-email", "email"),
        ("summary", "ab", "at least 3 characters"),
        ("summary", "much too long text", "at most 10 characters"),
        ("count", "0", "at least 1"),
        ("count", "101", "at most 100"),
        ("count", "abc", "valid number"),
        ("ratio", "nan", "valid number"),
        ("ratio", "NaN", "valid number"),
        ("ratio", "inf", "valid number"),
        ("ratio", "-Infinity", "valid number"),
        ("count", "inf", "valid number"),
        ("items", "[]", "required"),
        ("items", "  ", "required"),
        ("items", '["", "  "]', "required"),
        ("items", '["only one"]', "at least 2 items"),
        ("items", '["a", "b", "c", "d"]', "at most 3 items"),
        ("items", "not json", "valid list"),
        ("items", '{"a": 1}', "valid list"),
        ("items", "[1, 2]", "valid list"),
        ("tags", "nope", "valid list"),
    ],
)
def test_save_validation_errors(owner_token, template_id, field_name, value, contains):
    doc = _create_doc(owner_token, template_id)
    response = _put_values(
        owner_token, doc["id"], [{"field_name": field_name, "value": value}]
    )
    _assert_field_error(response, field_name, contains)


def test_unknown_field_422(owner_token, template_id):
    doc = _create_doc(owner_token, template_id)
    response = _put_values(
        owner_token, doc["id"], [{"field_name": "does_not_exist", "value": "x"}]
    )
    _assert_field_error(response, "does_not_exist", "not found")


def test_duplicate_field_in_payload_422(owner_token, template_id):
    doc = _create_doc(owner_token, template_id)
    response = _put_values(
        owner_token,
        doc["id"],
        [
            {"field_name": "title", "value": "first"},
            {"field_name": "title", "value": "second"},
        ],
    )
    _assert_field_error(response, "title", "Duplicate")

    # Nothing was persisted.
    values = client.get(
        f"/api/v1/documents/{doc['id']}/values", headers=_auth(owner_token)
    )
    assert values.json()["values"] == []


def test_validation_failure_saves_nothing(owner_token, template_id):
    doc = _create_doc(owner_token, template_id)
    response = _put_values(
        owner_token,
        doc["id"],
        [
            {"field_name": "title", "value": "ok"},
            {"field_name": "contact", "value": "bad"},
        ],
    )
    assert response.status_code == 422
    values = client.get(
        f"/api/v1/documents/{doc['id']}/values", headers=_auth(owner_token)
    )
    assert values.json()["values"] == []


@pytest.mark.parametrize(
    "field_name,value",
    [
        ("items", '["a", "b"]'),
        ("items", '["a", "b", "c"]'),
        ("tags", "[]"),
        ("tags", ""),
        ("ratio", "-3.5"),
        ("ratio", ""),
        ("count", "1"),
        ("count", "100"),
        ("summary", "abc"),
    ],
)
def test_save_valid_values(owner_token, template_id, field_name, value):
    doc = _create_doc(owner_token, template_id)
    response = _put_values(
        owner_token, doc["id"], [{"field_name": field_name, "value": value}]
    )
    assert response.status_code == 200, response.text


def test_malformed_rule_is_ignored_with_warning(owner_token, template_id, caplog):
    doc = _create_doc(owner_token, template_id)
    with caplog.at_level(logging.WARNING, logger="app.services.document_validator"):
        response = _put_values(
            owner_token, doc["id"], [{"field_name": "notes", "value": "x"}]
        )
    assert response.status_code == 200, response.text
    assert any("min:abc" in r.getMessage() for r in caplog.records)


# ── updated_at ────────────────────────────────────────────────────


def _backdate(document_id: int, when: datetime) -> None:
    with TestSession() as session:
        document = session.get(Document, document_id)
        document.updated_at = when
        session.commit()


def test_save_bumps_updated_at_and_list_order(owner_token, template_id):
    older = _create_doc(owner_token, template_id, name="Older")
    newer = _create_doc(owner_token, template_id, name="Newer")
    long_ago = datetime.utcnow() - timedelta(days=30)
    _backdate(older["id"], long_ago)
    _backdate(newer["id"], long_ago + timedelta(days=1))

    listed = client.get("/api/v1/documents", headers=_auth(owner_token)).json()
    ids = [d["id"] for d in listed]
    assert ids.index(newer["id"]) < ids.index(older["id"])

    saved = _put_values(
        owner_token, older["id"], [{"field_name": "title", "value": "Touched"}]
    )
    assert saved.status_code == 200, saved.text

    one = client.get(f"/api/v1/documents/{older['id']}", headers=_auth(owner_token))
    updated_at = datetime.fromisoformat(one.json()["updated_at"])
    assert updated_at > long_ago + timedelta(days=1)

    listed = client.get("/api/v1/documents", headers=_auth(owner_token)).json()
    ids = [d["id"] for d in listed]
    assert ids.index(older["id"]) < ids.index(newer["id"])


def test_document_value_schema_bounds() -> None:
    import pytest
    from pydantic import ValidationError

    from app.schemas.document import (
        MAX_DOCUMENT_VALUE_LENGTH,
        MAX_VALUES_PER_REQUEST,
        DocumentValueCreate,
        DocumentValuesBulkUpsert,
    )

    with pytest.raises(ValidationError):
        DocumentValueCreate(field_name="x", value="a" * (MAX_DOCUMENT_VALUE_LENGTH + 1))
    with pytest.raises(ValidationError):
        DocumentValuesBulkUpsert(
            values=[{"field_name": f"f{i}", "value": "v"} for i in range(MAX_VALUES_PER_REQUEST + 1)]
        )
