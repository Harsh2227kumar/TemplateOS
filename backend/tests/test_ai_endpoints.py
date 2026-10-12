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
