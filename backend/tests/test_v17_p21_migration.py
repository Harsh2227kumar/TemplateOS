"""
Migration b8e4c2a6d1f9 (V1.7 P2.1: template revisions, personal copies,
manual-edit versions, editor sessions) on a throwaway SQLite file, with data:

- upgrade backfills one 'upload' revision per template that has a file
- new columns / defaults / constraints exist and work
- downgrade drops everything again; upgrading again backfills again
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
PREVIOUS_REVISION = "a7d3f9c1e5b8"
REVISION = "b8e4c2a6d1f9"


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
    db_file = tmp_path / "editor.db"
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return db_file, environment


def _query(db_file: Path, sql: str, params=()) -> list[tuple]:
    with sqlite3.connect(db_file) as connection:
        return connection.execute(sql, params).fetchall()


def _seed(db_file: Path) -> None:
    with sqlite3.connect(db_file) as connection:
        connection.executescript(
            """
            INSERT INTO users (id, email, full_name, role) VALUES (1, 'a@x', 'Admin', 'org_admin');
            INSERT INTO templates (id, name, category, visibility, status, uploaded_by, version,
                                   original_file_path, processed_file_path, updated_at) VALUES
                (1, 'MoM', 'mom', 'public', 'active', 1, 3, 'templates/original/a.docx',
                 'templates/processed/a.docx', '2026-10-01 10:00:00'),
                (2, 'Raw', 'mom', 'private', 'uploaded', 1, 1, 'templates/original/b.docx', NULL,
                 '2026-10-02 10:00:00'),
                (3, 'Empty', 'mom', 'private', 'uploaded', 1, 1, NULL, NULL, '2026-10-03 10:00:00');
            INSERT INTO documents (id, template_id, created_by, name, status) VALUES (1, 1, 1, 'D', 'generated');
            INSERT INTO document_versions (id, document_id, version, values_snapshot) VALUES
                (1, 1, 1, '[]'), (2, 1, 2, '[]');
            """
        )


def test_upgrade_backfills_and_round_trips(migration_db) -> None:
    db_file, environment = migration_db
    _alembic(environment, "upgrade", PREVIOUS_REVISION)
    _seed(db_file)

    _alembic(environment, "upgrade", REVISION)

    assert _query(
        db_file,
        "SELECT template_id, revision, source, file_path, created_by, created_at "
        "FROM template_revisions ORDER BY template_id",
    ) == [
        (1, 3, "upload", "templates/processed/a.docx", 1, "2026-10-01 10:00:00"),
        (2, 1, "upload", "templates/original/b.docx", 1, "2026-10-02 10:00:00"),
    ]
    assert _query(db_file, "SELECT id, source, base_version_id FROM document_versions ORDER BY id") == [
        (1, "generated", None),
        (2, "generated", None),
    ]
    assert _query(db_file, "SELECT parent_template_id FROM templates ORDER BY id") == [(None,)] * 3

    engine = create_engine(environment["DATABASE_URL"])
    try:
        inspector = inspect(engine)
        assert {"template_revisions", "editor_sessions"} <= set(inspector.get_table_names())
        foreign = {fk["referred_table"]: fk for fk in inspector.get_foreign_keys("templates")}
        assert foreign["templates"]["options"].get("ondelete") == "SET NULL"
        unique = {tuple(c["column_names"]) for c in inspector.get_unique_constraints("template_revisions")}
        assert ("template_id", "revision") in unique
    finally:
        engine.dispose()

    with sqlite3.connect(db_file) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        # Personal copy pointing at its parent; manual-edit version with a base.
        connection.execute(
            "INSERT INTO templates (id, name, category, visibility, status, uploaded_by, parent_template_id) "
            "VALUES (4, 'MoM (my copy)', 'mom', 'private', 'active', 1, 1)"
        )
        connection.execute(
            "INSERT INTO document_versions (id, document_id, version, values_snapshot, source, base_version_id) "
            "VALUES (3, 1, 3, '[]', 'manual_edit', 2)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO document_versions (document_id, version, values_snapshot, source) "
                "VALUES (1, 4, '[]', 'imported')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO template_revisions (template_id, revision, source, file_path) "
                "VALUES (1, 3, 'clean', 'x.docx')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO template_revisions (template_id, revision, source, file_path) "
                "VALUES (1, 4, 'magic', 'x.docx')"
            )
        connection.execute(
            "INSERT INTO editor_sessions (session_key, target_type, template_id, source_path, user_id, expires_at) "
            "VALUES ('k1', 'template', 4, 'x.docx', 1, '2026-10-20 10:00:00')"
        )
        assert connection.execute("SELECT status FROM editor_sessions").fetchone() == ("open",)
        with pytest.raises(sqlite3.IntegrityError):  # template session without a template
            connection.execute(
                "INSERT INTO editor_sessions (session_key, target_type, document_id, source_path, user_id, expires_at) "
                "VALUES ('k2', 'template', 1, 'x.docx', 1, '2026-10-20 10:00:00')"
            )
        with pytest.raises(sqlite3.IntegrityError):  # duplicate key
            connection.execute(
                "INSERT INTO editor_sessions (session_key, target_type, document_id, source_path, user_id, expires_at) "
                "VALUES ('k1', 'document', 1, 'x.docx', 1, '2026-10-20 10:00:00')"
            )
        # Deleting the parent keeps the copy; deleting the base version keeps the edit.
        connection.execute("DELETE FROM document_versions WHERE id = 2")
        assert connection.execute("SELECT base_version_id FROM document_versions WHERE id = 3").fetchone() == (None,)
        connection.commit()

    _alembic(environment, "downgrade", PREVIOUS_REVISION)
    engine = create_engine(environment["DATABASE_URL"])
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert not {"template_revisions", "editor_sessions"} & tables
        assert "parent_template_id" not in {c["name"] for c in inspector.get_columns("templates")}
        assert not {"source", "base_version_id"} & {c["name"] for c in inspector.get_columns("document_versions")}
    finally:
        engine.dispose()

    _alembic(environment, "upgrade", "head")
    assert len(_query(db_file, "SELECT id FROM template_revisions")) == 2


def test_single_head_is_this_revision() -> None:
    environment = {
        **os.environ,
        "DATABASE_URL": "sqlite://",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
    }
    heads = _alembic(environment, "heads").stdout.split()
    assert heads[0] == REVISION
    assert heads.count("(head)") == 1
