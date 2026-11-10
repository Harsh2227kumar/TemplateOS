"""
Migration a3c7e1f9b2d6 (template access scopes) on a throwaway SQLite file:
upgrade from d2f9b4e7c1a8 backfills scope_* from the uploader, downgrade
drops the columns, and upgrading again works.
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

BACKEND_DIR = Path(__file__).resolve().parents[1]
NEW_COLUMNS = {"scope_organization", "scope_department", "allowed_roles"}


def _alembic(environment: dict, *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini.example", *args],
        cwd=BACKEND_DIR,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def _template_columns(engine) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns("templates")}


def test_access_scope_migration_up_down_up(tmp_path: Path) -> None:
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'access.db').as_posix()}",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
    }
    _alembic(environment, "upgrade", "d2f9b4e7c1a8")

    engine = create_engine(environment["DATABASE_URL"])
    try:
        assert not NEW_COLUMNS & _template_columns(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, full_name, role, organization, department) VALUES "
                "(1, 'a@x', 'A', 'org_admin', ' State University ', NULL), "
                "(2, 'b@x', 'B', 'department_admin', 'State University', 'Computer Science'), "
                "(3, 'c@x', 'C', 'faculty', '', '  ')"
            )
            connection.exec_driver_sql(
                "INSERT INTO templates (id, name, category, visibility, status, uploaded_by) VALUES "
                "(1, 'Letterhead', 'letter', 'organization', 'active', 1), "
                "(2, 'CS form', 'notice', 'department', 'active', 2), "
                "(3, 'Public', 'notice', 'public', 'active', 2), "
                "(4, 'Blank dept', 'notice', 'department', 'active', 3)"
            )
    finally:
        engine.dispose()

    _alembic(environment, "upgrade", "head")
    engine = create_engine(environment["DATABASE_URL"])
    try:
        assert NEW_COLUMNS <= _template_columns(engine)
        with engine.connect() as connection:
            rows = connection.exec_driver_sql(
                "SELECT id, scope_organization, scope_department, allowed_roles "
                "FROM templates ORDER BY id"
            ).all()
        assert [tuple(row) for row in rows] == [
            (1, "State University", None, None),
            (2, "State University", "Computer Science", None),
            (3, None, None, None),
            (4, None, None, None),
        ]
    finally:
        engine.dispose()

    _alembic(environment, "downgrade", "d2f9b4e7c1a8")
    engine = create_engine(environment["DATABASE_URL"])
    try:
        assert not NEW_COLUMNS & _template_columns(engine)
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM templates").scalar_one() == 4
    finally:
        engine.dispose()

    _alembic(environment, "upgrade", "head")
    engine = create_engine(environment["DATABASE_URL"])
    try:
        assert NEW_COLUMNS <= _template_columns(engine)
        with engine.connect() as connection:
            assert (
                connection.exec_driver_sql(
                    "SELECT scope_department FROM templates WHERE id = 2"
                ).scalar_one()
                == "Computer Science"
            )
    finally:
        engine.dispose()
