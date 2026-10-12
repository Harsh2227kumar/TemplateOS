"""
Tests for V1.5 Phase 1 — Basic AI Actions.

Member 3 — Database / Integration Developer (data layer):
1. ImproveTextRequest strictly validates action_type, required fields and
   original_text (non-blank, length-capped).
2. log_ai_generation stores document_id; deleting the document SET NULLs
   it (the audit row survives), with SQLite FK enforcement on.
3. Migration c4d8e2f6a1b3 adds the FK on top of the V1.4 documents
   migration, clears orphaned document_ids, and downgrades cleanly.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault(
    "JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests"
)
os.environ["API_V1_PREFIX"] = "/api/v1"
# This module sorts before the other AI test files, so it may be the first to
# import app.core.config: set the same model default they rely on, or the
# settings singleton is created without it on machines with no .env.
os.environ.setdefault("BEDROCK_MODEL_SUGGESTIONS", "test-model-id")

from app.crud.ai_generation_crud import log_ai_generation
from app.crud.document_crud import create_document, delete_document
from app.db.base import Base
from app.models.ai_generation import AiGeneration
from app.models.template import Template
from app.models.user import User
from app.schemas.ai import (
    AI_TEXT_ACTIONS,
    MAX_IMPROVE_TEXT_CHARS,
    ImproveTextRequest,
)

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def _enable_sqlite_fk(dbapi_connection, _record):
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=test_engine)
    session = TestSession()
    yield session
    session.close()
    Base.metadata.drop_all(bind=test_engine)


def _make_user(db, email: str = "ai_writer@example.com") -> User:
    user = User(email=email, full_name="AI Writer", role="normal_user")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_template(db, user_id: int) -> Template:
    template = Template(
        name="AI Template", category="notice", visibility="private", uploaded_by=user_id
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


# ── 1. Schema validation ────────────────────────────────────────────────

VALID_REQUEST = {
    "template_id": 1,
    "field_name": "summary",
    "original_text": "this are a rough sentence",
    "action_type": "grammar",
}


@pytest.mark.parametrize("action", AI_TEXT_ACTIONS)
def test_improve_text_request_accepts_each_action(action):
    req = ImproveTextRequest(**{**VALID_REQUEST, "action_type": action})
    assert req.action_type == action
    assert req.document_id is None


def test_ai_text_actions_are_the_four_phase1_actions():
    assert set(AI_TEXT_ACTIONS) == {"grammar", "tone", "concise", "formal"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"action_type": "rewrite"},
        {"action_type": "GRAMMAR"},
        {"action_type": ""},
        {"original_text": ""},
        {"original_text": "   \n "},
        {"original_text": "x" * (MAX_IMPROVE_TEXT_CHARS + 1)},
        {"field_name": ""},
        {"field_name": "f" * 101},
        {"template_id": "not-a-number"},
    ],
)
def test_improve_text_request_rejects_invalid(overrides):
    with pytest.raises(ValidationError):
        ImproveTextRequest(**{**VALID_REQUEST, **overrides})


@pytest.mark.parametrize("missing", ["template_id", "field_name", "original_text", "action_type"])
def test_improve_text_request_requires_fields(missing):
    payload = {k: v for k, v in VALID_REQUEST.items() if k != missing}
    with pytest.raises(ValidationError):
        ImproveTextRequest(**payload)


def test_improve_text_request_accepts_document_id():
    req = ImproveTextRequest(**{**VALID_REQUEST, "document_id": 7})
    assert req.document_id == 7


# ── 2. CRUD + FK behavior ───────────────────────────────────────────────


def test_log_ai_generation_stores_document_id(db):
    user = _make_user(db)
    template = _make_template(db, user.id)
    doc = create_document(db, template.id, user.id)

    row = log_ai_generation(
        db,
        action_type="grammar",
        model="test-nova-micro",
        template_id=template.id,
        document_id=doc.id,
        created_by=user.id,
        field_key="summary",
    )

    assert row.document_id == doc.id
    assert row.field_key == "summary"
    assert row.status == "success"


def test_log_ai_generation_document_id_defaults_to_none(db):
    user = _make_user(db)
    row = log_ai_generation(
        db, action_type="suggest_fields", model="m", created_by=user.id
    )
    assert row.document_id is None


def test_log_ai_generation_rejects_unknown_document(db):
    user = _make_user(db)
    with pytest.raises(Exception):
        log_ai_generation(
            db, action_type="grammar", model="m", document_id=9999, created_by=user.id
        )
    db.rollback()


def test_deleting_document_sets_ai_generation_document_id_null(db):
    user = _make_user(db)
    template = _make_template(db, user.id)
    doc = create_document(db, template.id, user.id)
    row = log_ai_generation(
        db,
        action_type="tone",
        model="m",
        template_id=template.id,
        document_id=doc.id,
        created_by=user.id,
    )

    assert delete_document(db, doc.id) is True
    db.expire_all()

    survivor = db.get(AiGeneration, row.id)
    assert survivor is not None
    assert survivor.document_id is None
    assert survivor.template_id == template.id


# ── 3. Migration ────────────────────────────────────────────────────────


def test_ai_generations_document_fk_migration(tmp_path: Path) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'ai-doc-fk.db').as_posix()}",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
    }
    command = [sys.executable, "-m", "alembic", "-c", "alembic.ini.example"]

    def alembic(*args: str) -> None:
        subprocess.run(
            [*command, *args],
            cwd=backend_dir,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

    # Start on the V1.4 documents revision with an orphaned document_id.
    alembic("upgrade", "9a8b7c6d5e4f")
    engine = create_engine(environment["DATABASE_URL"])
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (email, full_name, role) "
                "VALUES ('fk_owner@example.com', 'FK Owner', 'normal_user')"
            )
            connection.exec_driver_sql(
                "INSERT INTO ai_generations (action_type, model, document_id, created_by) "
                "VALUES ('suggest_fields', 'm', 424242, 1)"
            )
    finally:
        engine.dispose()

    alembic("upgrade", "c4d8e2f6a1b3")

    engine = create_engine(environment["DATABASE_URL"])

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    try:
        foreign_keys = inspect(engine).get_foreign_keys("ai_generations")
        doc_fk = [fk for fk in foreign_keys if fk["referred_table"] == "documents"]
        assert len(doc_fk) == 1
        assert doc_fk[0]["constrained_columns"] == ["document_id"]
        assert doc_fk[0]["options"].get("ondelete") == "SET NULL"
        # The earlier FKs survived the batch table rebuild.
        referred = {fk["referred_table"] for fk in foreign_keys}
        assert {"templates", "users", "documents"} <= referred

        with engine.begin() as connection:
            orphan = connection.exec_driver_sql(
                "SELECT document_id FROM ai_generations WHERE id = 1"
            ).scalar_one()
            assert orphan is None

            # ON DELETE SET NULL fires on the migration-created schema.
            connection.exec_driver_sql(
                "INSERT INTO templates (name, category, visibility, status, uploaded_by) "
                "VALUES ('FK Template', 'notice', 'private', 'uploaded', 1)"
            )
            connection.exec_driver_sql(
                "INSERT INTO documents (template_id, created_by) VALUES (1, 1)"
            )
            connection.exec_driver_sql(
                "INSERT INTO ai_generations (action_type, model, document_id, created_by) "
                "VALUES ('grammar', 'm', 1, 1)"
            )
            connection.exec_driver_sql("DELETE FROM documents WHERE id = 1")
            remaining = connection.exec_driver_sql(
                "SELECT document_id FROM ai_generations WHERE id = 2"
            ).scalar_one()
            assert remaining is None
    finally:
        engine.dispose()

    # Downgrade removes only the FK; the column and table stay.
    alembic("downgrade", "9a8b7c6d5e4f")
    engine = create_engine(environment["DATABASE_URL"])
    try:
        inspector = inspect(engine)
        assert "document_id" in {c["name"] for c in inspector.get_columns("ai_generations")}
        assert all(
            fk["referred_table"] != "documents"
            for fk in inspector.get_foreign_keys("ai_generations")
        )
    finally:
        engine.dispose()

    # Re-runnable.
    alembic("upgrade", "head")


# ═══ Member 2 — service + POST /api/v1/ai/improve-text ══════════════════
#
# The Bedrock call is always mocked: ai_service.improve_text for endpoint
# tests, the instructor client for service tests. settings are patched
# explicitly because config.py exports the developer's real .env AI vars.

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.document import Document
from app.models.template_field import TemplateField
from app.services import ai_service
from app.services.ai_service import AiUnavailableError

NOVA_MICRO = "test-nova-micro"
NOVA_LITE = "test-nova-lite"
URL = "/api/v1/ai/improve-text"


@pytest.fixture()
def nova_settings(monkeypatch):
    monkeypatch.setattr(settings, "aws_region", "ap-south-1")
    monkeypatch.setattr(settings, "bedrock_model_nova_micro", NOVA_MICRO)
    monkeypatch.setattr(settings, "bedrock_model_nova_lite", NOVA_LITE)


# ── Service: model routing, config errors, provider errors ──────────────


@pytest.mark.parametrize(
    "action, model",
    [("grammar", NOVA_MICRO), ("tone", NOVA_LITE), ("concise", NOVA_LITE), ("formal", NOVA_LITE)],
)
def test_model_for_action_routes_to_nova(nova_settings, action, model):
    assert ai_service.model_for_action(action) == model


class _FakeCompletions:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


def _fake_client(completions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_improve_text_calls_nova_and_strips_result(nova_settings, monkeypatch):
    completions = _FakeCompletions(
        result=ai_service.TextImprovement(improved_text="  Fixed text.\n")
    )
    monkeypatch.setattr(ai_service, "_build_bedrock_client", lambda: _fake_client(completions))

    assert ai_service.improve_text("concise", "some long text") == "Fixed text."
    call = completions.calls[0]
    assert call["model"] == NOVA_LITE
    assert call["response_model"] is ai_service.TextImprovement
    assert call["messages"][0]["role"] == "system"
    assert "some long text" in call["messages"][1]["content"]


def test_improve_text_unknown_action_raises_value_error(nova_settings):
    with pytest.raises(ValueError):
        ai_service.improve_text("rewrite", "text")


def test_improve_text_missing_model_id_is_unavailable(nova_settings, monkeypatch):
    monkeypatch.setattr(settings, "bedrock_model_nova_micro", "")
    with pytest.raises(AiUnavailableError, match="BEDROCK_MODEL_NOVA_MICRO"):
        ai_service.improve_text("grammar", "text")


def test_improve_text_without_region_is_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "aws_region", None)
    with pytest.raises(AiUnavailableError, match="AWS_REGION"):
        ai_service.improve_text("grammar", "text")


def test_improve_text_empty_model_output_is_unavailable(nova_settings, monkeypatch):
    completions = _FakeCompletions(result=ai_service.TextImprovement(improved_text="   "))
    monkeypatch.setattr(ai_service, "_build_bedrock_client", lambda: _fake_client(completions))
    with pytest.raises(AiUnavailableError, match="empty"):
        ai_service.improve_text("grammar", "text")


class _FakeClientError(Exception):
    """Shaped like botocore ClientError: HTTP status in response metadata."""

    def __init__(self, status_code: int):
        super().__init__(f"Bedrock said {status_code}")
        self.response = {"ResponseMetadata": {"HTTPStatusCode": status_code}}


@pytest.mark.parametrize(
    "status_code, expected",
    [(403, "HTTP 403"), (400, "BEDROCK_MODEL_NOVA_LITE"), (429, "throttled")],
)
def test_improve_text_provider_errors_are_classified(
    nova_settings, monkeypatch, status_code, expected
):
    completions = _FakeCompletions(error=_FakeClientError(status_code))
    monkeypatch.setattr(ai_service, "_build_bedrock_client", lambda: _fake_client(completions))
    with pytest.raises(AiUnavailableError, match=expected):
        ai_service.improve_text("formal", "text")


# ── Endpoint ────────────────────────────────────────────────────────────

api_client = TestClient(app)


def _override_get_db():
    with TestSession() as session:
        yield session


@pytest.fixture()
def api(nova_settings):
    old = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=test_engine)
    yield api_client
    Base.metadata.drop_all(bind=test_engine)
    if old is not None:
        app.dependency_overrides[get_db] = old
    else:
        app.dependency_overrides.pop(get_db, None)


def _token(email: str) -> str:
    api_client.post(
        "/api/v1/auth/signup",
        json={"full_name": "AI User", "email": email, "password": "strong-password"},
    )
    login = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "strong-password"}
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _user_id(email: str) -> int:
    with TestSession() as session:
        return session.query(User).filter_by(email=email).one().id


@pytest.fixture()
def world(api):
    """Owner + stranger, a private template with mixed fields, one draft."""
    owner_token = _token("ai_owner@example.com")
    stranger_token = _token("ai_stranger@example.com")
    owner_id = _user_id("ai_owner@example.com")
    with TestSession() as session:
        template = Template(
            name="AI Endpoint Template",
            category="mom",
            visibility="private",
            uploaded_by=owner_id,
            status="active",
        )
        other = Template(
            name="Other Template", category="mom", visibility="private", uploaded_by=owner_id
        )
        session.add_all([template, other])
        session.flush()
        for order, (name, ftype, ai) in enumerate(
            [
                ("summary", "textarea", True),
                ("title", "text", True),
                ("notes", "textarea", False),
                ("items", "list", True),
            ]
        ):
            session.add(
                TemplateField(
                    template_id=template.id,
                    field_name=name,
                    field_type=ftype,
                    ai_enabled=ai,
                    display_order=order,
                )
            )
        doc = Document(template_id=template.id, created_by=owner_id)
        other_doc = Document(template_id=other.id, created_by=owner_id)
        session.add_all([doc, other_doc])
        session.commit()
        return SimpleNamespace(
            owner=owner_token,
            stranger=stranger_token,
            owner_id=owner_id,
            template_id=template.id,
            document_id=doc.id,
            other_document_id=other_doc.id,
        )


def _body(world, **overrides) -> dict:
    return {
        "template_id": world.template_id,
        "document_id": world.document_id,
        "field_name": "summary",
        "original_text": "we has discussed the budget",
        "action_type": "grammar",
        **overrides,
    }


def _audit_rows() -> list[AiGeneration]:
    with TestSession() as session:
        return list(session.query(AiGeneration).order_by(AiGeneration.id))


def _mock_improve(monkeypatch, result="We discussed the budget."):
    calls = []

    def fake(action_type, original_text):
        calls.append((action_type, original_text))
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(ai_service, "improve_text", fake)
    return calls


def test_improve_text_success_returns_text_and_logs(world, monkeypatch):
    calls = _mock_improve(monkeypatch)

    response = api_client.post(URL, json=_body(world), headers=_auth(world.owner))

    assert response.status_code == 200, response.text
    assert response.json() == {"improved_text": "We discussed the budget."}
    assert calls == [("grammar", "we has discussed the budget")]
    rows = _audit_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "success"
    assert row.action_type == "grammar"
    assert row.model == NOVA_MICRO
    assert row.template_id == world.template_id
    assert row.document_id == world.document_id
    assert row.field_key == "summary"
    assert row.created_by == world.owner_id


def test_improve_text_without_document_id(world, monkeypatch):
    _mock_improve(monkeypatch)
    response = api_client.post(
        URL,
        json=_body(world, document_id=None, action_type="formal", field_name="title"),
        headers=_auth(world.owner),
    )
    assert response.status_code == 200, response.text
    row = _audit_rows()[0]
    assert row.document_id is None
    assert row.model == NOVA_LITE


def test_improve_text_ai_unavailable_returns_503_and_logs_error(world, monkeypatch):
    _mock_improve(monkeypatch, AiUnavailableError("AI is currently unavailable: boom"))

    response = api_client.post(URL, json=_body(world), headers=_auth(world.owner))

    assert response.status_code == 503
    assert "boom" in response.json()["detail"]
    row = _audit_rows()[0]
    assert row.status == "error"
    assert row.document_id == world.document_id
    assert "boom" in row.detail


def test_improve_text_unconfigured_model_logs_placeholder(world, monkeypatch):
    monkeypatch.setattr(settings, "bedrock_model_nova_micro", "")
    _mock_improve(monkeypatch, AiUnavailableError("AI is not configured"))
    response = api_client.post(URL, json=_body(world), headers=_auth(world.owner))
    assert response.status_code == 503
    assert _audit_rows()[0].model == "unconfigured"


def test_improve_text_requires_auth(world):
    assert api_client.post(URL, json=_body(world)).status_code == 401


@pytest.mark.parametrize(
    "overrides, code",
    [
        ({"template_id": 99999}, 404),
        ({"document_id": 99999}, 404),
        ({"field_name": "missing_field"}, 404),
        ({"field_name": "notes"}, 422),  # ai_enabled = False
        ({"field_name": "items"}, 422),  # list field
        ({"action_type": "rewrite"}, 422),
        ({"original_text": "   "}, 422),
    ],
)
def test_improve_text_rejects_bad_requests_without_calling_ai(world, monkeypatch, overrides, code):
    calls = _mock_improve(monkeypatch)
    response = api_client.post(URL, json=_body(world, **overrides), headers=_auth(world.owner))
    assert response.status_code == code, response.text
    assert calls == []
    assert _audit_rows() == []


def test_improve_text_document_from_other_template_is_422(world, monkeypatch):
    calls = _mock_improve(monkeypatch)
    response = api_client.post(
        URL, json=_body(world, document_id=world.other_document_id), headers=_auth(world.owner)
    )
    assert response.status_code == 422
    assert calls == []


def test_improve_text_stranger_cannot_use_private_template(world, monkeypatch):
    calls = _mock_improve(monkeypatch)
    response = api_client.post(URL, json=_body(world), headers=_auth(world.stranger))
    assert response.status_code == 403
    assert calls == []
    assert _audit_rows() == []


def test_improve_text_stranger_cannot_use_owners_document(world, monkeypatch):
    with TestSession() as session:
        session.get(Template, world.template_id).visibility = "public"
        session.commit()
    calls = _mock_improve(monkeypatch)

    response = api_client.post(URL, json=_body(world), headers=_auth(world.stranger))
    assert response.status_code == 403
    assert calls == []

    # Same public template without a document is allowed.
    ok = api_client.post(URL, json=_body(world, document_id=None), headers=_auth(world.stranger))
    assert ok.status_code == 200, ok.text
