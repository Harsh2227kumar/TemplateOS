"""
Migration f2a6c8e4b7d1 (V1.7 P2.2: AI fill chat) on a throwaway SQLite file:
tables, UNIQUE / CHECK constraints, CASCADE from documents, the template
baseline columns; downgrade removes all of it; upgrading again works.
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
PREVIOUS_REVISION = "e7b3c1d9a5f4"
REVISION = "f2a6c8e4b7d1"


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
    db_file = tmp_path / "ai_fill.db"
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return db_file, environment


def test_upgrade_constraints_cascade_and_round_trip(migration_db) -> None:
    db_file, environment = migration_db
    _alembic(environment, "upgrade", PREVIOUS_REVISION)
    with sqlite3.connect(db_file) as connection:
        connection.executescript(
            """
            INSERT INTO users (id, email, full_name, role) VALUES (1, 'a@x', 'A', 'faculty');
            INSERT INTO templates (id, name, category, visibility, status, uploaded_by)
                VALUES (1, 'Report', 'report', 'private', 'active', 1);
            INSERT INTO documents (id, template_id, created_by, name, status) VALUES (1, 1, 1, 'D', 'draft');
            INSERT INTO documents (id, template_id, created_by, name, status) VALUES (2, 1, 1, 'E', 'draft');
            """
        )

    _alembic(environment, "upgrade", REVISION)

    engine = create_engine(environment["DATABASE_URL"])
    try:
        inspector = inspect(engine)
        assert {"ai_fill_sessions", "ai_fill_messages"} <= set(inspector.get_table_names())
        template_columns = {column["name"] for column in inspector.get_columns("templates")}
        assert {"baseline_pages", "baseline_pages_version"} <= template_columns
        message_columns = {column["name"] for column in inspector.get_columns("ai_fill_messages")}
        assert {"turn", "role", "content", "answers", "proposals", "questions", "stage", "model"} <= message_columns
        for table in ("ai_fill_sessions", "ai_fill_messages"):
            assert {fk["options"].get("ondelete") for fk in inspector.get_foreign_keys(table)} == {"CASCADE"}
    finally:
        engine.dispose()

    with sqlite3.connect(db_file) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        # Existing rows are untouched; the new template columns start empty.
        assert connection.execute("SELECT baseline_pages, baseline_pages_version FROM templates").fetchone() == (
            None,
            None,
        )
        connection.execute("INSERT INTO ai_fill_sessions (id, document_id, user_id) VALUES (1, 1, 1)")
        assert connection.execute(
            "SELECT status, turn_count, filled_count FROM ai_fill_sessions"
        ).fetchone() == ("active", 0, 0)
        # One chat per document.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO ai_fill_sessions (document_id, user_id) VALUES (1, 1)")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO ai_fill_sessions (document_id, user_id, status) VALUES (2, 1, 'paused')")

        connection.execute(
            "INSERT INTO ai_fill_messages (session_id, turn, role, content) VALUES (1, 1, 'user', 'hello')"
        )
        connection.execute(
            "INSERT INTO ai_fill_messages (session_id, turn, role, content, stage) "
            "VALUES (1, 1, 'assistant', 'hi', 'asking')"
        )
        with pytest.raises(sqlite3.IntegrityError):  # one row per (turn, role)
            connection.execute(
                "INSERT INTO ai_fill_messages (session_id, turn, role, content) VALUES (1, 1, 'user', 'again')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO ai_fill_messages (session_id, turn, role, content) VALUES (1, 2, 'system', 'x')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO ai_fill_messages (session_id, turn, role, content, stage) "
                "VALUES (1, 2, 'assistant', 'x', 'thinking')"
            )

        # Deleting the document removes its chat.
        connection.execute("DELETE FROM documents WHERE id = 1")
        assert connection.execute("SELECT count(*) FROM ai_fill_sessions").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM ai_fill_messages").fetchone() == (0,)
        connection.commit()

    _alembic(environment, "downgrade", PREVIOUS_REVISION)
    engine = create_engine(environment["DATABASE_URL"])
    try:
        inspector = inspect(engine)
        assert not {"ai_fill_sessions", "ai_fill_messages"} & set(inspector.get_table_names())
        template_columns = {column["name"] for column in inspector.get_columns("templates")}
        assert not {"baseline_pages", "baseline_pages_version"} & template_columns
    finally:
        engine.dispose()
    with sqlite3.connect(db_file) as connection:
        assert connection.execute("SELECT name FROM documents").fetchall() == [("E",)]
    _alembic(environment, "upgrade", "head")


def test_single_head() -> None:
    environment = {
        **os.environ,
        "DATABASE_URL": "sqlite://",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
    }
    heads = _alembic(environment, "heads").stdout.split()
    # Later revisions build on this one; there must still be a single head.
    assert heads.count("(head)") == 1
