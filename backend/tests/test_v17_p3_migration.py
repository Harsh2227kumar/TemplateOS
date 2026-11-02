"""
Migration c3f7a9d2e6b1 (V1.7 P3: download_history + audit_logs) on a
throwaway SQLite file: tables, indexes, CHECK and SET NULL foreign keys
exist; downgrade drops both; upgrading again works.
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

BACKEND_DIR = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "b8e4c2a6d1f9"
REVISION = "c3f7a9d2e6b1"


def _alembic(environment: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini.example", *args],
        cwd=BACKEND_DIR,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def migration_db(tmp_path: Path):
    db_file = tmp_path / "audit.db"
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return db_file, environment


def test_upgrade_constraints_and_round_trip(migration_db) -> None:
    db_file, environment = migration_db
    _alembic(environment, "upgrade", PREVIOUS_REVISION)
    with sqlite3.connect(db_file) as connection:
        connection.executescript(
            """
            INSERT INTO organizations (id, name) VALUES (1, 'SIT');
            INSERT INTO departments (id, organization_id, name) VALUES (1, 1, 'CSE');
            INSERT INTO users (id, email, full_name, role) VALUES (1, 'a@x', 'A', 'faculty');
            INSERT INTO templates (id, name, category, visibility, status, uploaded_by)
                VALUES (1, 'MoM', 'mom', 'private', 'active', 1);
            INSERT INTO documents (id, template_id, created_by, name, status) VALUES (1, 1, 1, 'D', 'generated');
            INSERT INTO document_versions (id, document_id, version, values_snapshot) VALUES (1, 1, 1, '[]');
            """
        )

    _alembic(environment, "upgrade", REVISION)

    engine = create_engine(environment["DATABASE_URL"])
    try:
        inspector = inspect(engine)
        assert {"download_history", "audit_logs"} <= set(inspector.get_table_names())
        history_indexes = {i["name"]: i["column_names"] for i in inspector.get_indexes("download_history")}
        assert history_indexes["ix_download_history_user_downloaded"] == ["user_id", "downloaded_at"]
        assert history_indexes["ix_download_history_document_downloaded"] == ["document_id", "downloaded_at"]
        audit_indexes = {i["name"]: i["column_names"] for i in inspector.get_indexes("audit_logs")}
        assert audit_indexes["ix_audit_logs_entity"] == ["entity_type", "entity_id"]
        assert {"ix_audit_logs_action", "ix_audit_logs_created_at", "ix_audit_logs_organization_id"} <= set(
            audit_indexes
        )
        for table in ("download_history", "audit_logs"):
            assert {fk["options"].get("ondelete") for fk in inspector.get_foreign_keys(table)} == {"SET NULL"}
    finally:
        engine.dispose()

    with sqlite3.connect(db_file) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO download_history (user_id, document_id, version_id, version, version_source, format, "
            "document_name, file_name) VALUES (1, 1, 1, 1, 'generated', 'pdf', 'D', 'd.pdf')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO download_history (format, document_name, file_name) VALUES ('xlsx', 'D', 'd.xlsx')"
            )
        connection.execute(
            "INSERT INTO audit_logs (actor_id, actor_email, action, entity_type, entity_id, organization_id, "
            "department_id, summary) VALUES (1, 'a@x', 'document.download', 'document', 1, 1, 1, 'x')"
        )
        assert connection.execute("SELECT downloaded_at IS NOT NULL FROM download_history").fetchone() == (1,)
        connection.execute("DELETE FROM document_versions")
        connection.execute("DELETE FROM documents")
        connection.execute("DELETE FROM departments")
        assert connection.execute(
            "SELECT document_id, version_id, version, version_source FROM download_history"
        ).fetchone() == (None, None, 1, "generated")
        assert connection.execute("SELECT organization_id, department_id FROM audit_logs").fetchone() == (1, None)
        connection.commit()

    _alembic(environment, "downgrade", PREVIOUS_REVISION)
    engine = create_engine(environment["DATABASE_URL"])
    try:
        assert not {"download_history", "audit_logs"} & set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    _alembic(environment, "upgrade", "head")


def test_single_head_is_this_revision() -> None:
    environment = {
        **os.environ,
        "DATABASE_URL": "sqlite://",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
    }
    heads = _alembic(environment, "heads").stdout.split()
    assert heads[0] == REVISION
    assert heads.count("(head)") == 1
