"""
Migration d5e1a7c3b9f2 (institutes, user identity fields, approver
assignments) on a throwaway SQLite file: upgrade from c3f7a9d2e6b1 backfills
institutes / member types / missing template scopes without deleting
anything, downgrade removes only what it added (and keeps the lower(name)
indexes), and upgrading again works.
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

BACKEND_DIR = Path(__file__).resolve().parents[1]
REVISION = "d5e1a7c3b9f2"
PREVIOUS = "c3f7a9d2e6b1"


def _alembic(environment: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini.example", *args],
        cwd=BACKEND_DIR,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def _indexes(engine, table: str) -> set[str]:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?", (table,)
        ).fetchall()
    return {row[0] for row in rows}


def test_institutes_migration_up_down_up(tmp_path: Path) -> None:
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'inst.db').as_posix()}",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
    }
    _alembic(environment, "upgrade", PREVIOUS)
    engine = create_engine(environment["DATABASE_URL"])
    try:
        with engine.begin() as c:
            c.exec_driver_sql("INSERT INTO organizations (id, name) VALUES (1, 'Demo Org')")
            c.exec_driver_sql(
                "INSERT INTO departments (id, organization_id, name) VALUES "
                "(1, 1, 'Academic Affairs'), (2, 1, 'Computer Science')"
            )
            c.exec_driver_sql(
                "INSERT INTO users (id, email, full_name, role, organization_id, department_id) VALUES "
                "(1, 'a@x', 'A', 'super_admin', 1, NULL), (2, 'b@x', 'B', 'faculty', 1, 2), "
                "(3, 'c@x', 'C', 'approver', 1, 1), (4, 'd@x', 'D', 'normal_user', 1, NULL)"
            )
            c.exec_driver_sql(
                "INSERT INTO templates (id, name, category, visibility, uploaded_by, status, version, "
                "is_locked, requires_approval) VALUES "
                "(1, 't1', 'notice', 'department', 2, 'uploaded', 1, 0, 0), "
                "(2, 't2', 'notice', 'organization', 4, 'uploaded', 1, 0, 0)"
            )

        _alembic(environment, "upgrade", REVISION)
        with engine.connect() as c:
            institutes = c.exec_driver_sql("SELECT id, organization_id, name, code FROM institutes").fetchall()
            assert institutes == [(1, 1, "Demo Org", "MAIN")]
            assert c.exec_driver_sql("SELECT institute_id FROM departments ORDER BY id").fetchall() == [(1,), (1,)]
            users = c.exec_driver_sql(
                "SELECT id, role, member_type, institute_id, is_active FROM users ORDER BY id"
            ).fetchall()
            assert users == [
                (1, "super_admin", None, None, 1),
                (2, "faculty", "faculty", 1, 1),
                (3, "approver", "staff", 1, 1),
                (4, "normal_user", "staff", None, 1),
            ]
            templates = c.exec_driver_sql(
                "SELECT id, scope_organization_id, scope_department_id, scope_institute_id "
                "FROM templates ORDER BY id"
            ).fetchall()
            assert templates == [(1, 1, 2, 1), (2, 1, None, None)]
        assert "uq_organizations_name_lower" in _indexes(engine, "organizations")
        assert {"uq_departments_institute_name_lower", "uq_departments_institute_code"} <= _indexes(
            engine, "departments"
        )

        _alembic(environment, "downgrade", PREVIOUS)
        assert "institutes" not in inspect(engine).get_table_names()
        assert "approver_assignments" not in inspect(engine).get_table_names()
        assert "login_id" not in {col["name"] for col in inspect(engine).get_columns("users")}
        with engine.connect() as c:
            assert c.exec_driver_sql("SELECT count(*) FROM users").scalar() == 4
            assert c.exec_driver_sql("SELECT count(*) FROM templates").scalar() == 2
        assert "uq_organizations_name_lower" in _indexes(engine, "organizations")
        assert "uq_departments_org_name_lower" in _indexes(engine, "departments")
    finally:
        engine.dispose()
    _alembic(environment, "upgrade", "head")


def test_single_head_follows_this_revision() -> None:
    environment = {
        **os.environ,
        "DATABASE_URL": "sqlite://",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
    }
    heads = _alembic(environment, "heads").stdout.split()
    assert len(heads) >= 2  # "<rev> (head)": newer revisions follow this one
    assert heads.count("(head)") == 1
