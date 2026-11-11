"""
Migration e7b3c1d9a5f4 (EkLink sync) on a throwaway SQLite file: upgrade
from d5e1a7c3b9f2 adds sync_state, is_demo flags and the approver mirror
columns, gives the demo directory its EkLink codes and marks the local demo
users; downgrade restores the old codes and removes only what it added
(the lower(name) indexes survive); upgrading again works.
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

BACKEND_DIR = Path(__file__).resolve().parents[1]
REVISION = "e7b3c1d9a5f4"
PREVIOUS = "d5e1a7c3b9f2"


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


def _columns(engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


def test_eklink_sync_migration_up_down_up(tmp_path: Path) -> None:
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'sync.db').as_posix()}",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
    }
    _alembic(environment, "upgrade", PREVIOUS)
    engine = create_engine(environment["DATABASE_URL"])
    try:
        with engine.begin() as c:
            c.exec_driver_sql(
                "INSERT INTO organizations (id, name, code) VALUES "
                "(1, 'TemplateOS Demo Institute', NULL), (2, 'Symbiosis', 'SIU')"
            )
            c.exec_driver_sql(
                "INSERT INTO institutes (id, organization_id, name, code) VALUES "
                "(1, 1, 'TemplateOS Demo Institute', 'MAIN'), (2, 2, 'SIT', 'SIT')"
            )
            c.exec_driver_sql(
                "INSERT INTO departments (id, organization_id, institute_id, name, code) VALUES "
                "(1, 1, 1, 'Academic Affairs', NULL), (2, 1, 1, 'Computer Science', NULL), "
                "(3, 2, 2, 'Computer Science and Engineering', 'CSE')"
            )
            c.exec_driver_sql(
                "INSERT INTO users (id, email, full_name, role, organization_id, eklink_sub, login_id) VALUES "
                "(1, 'super.admin@example.com', 'S', 'super_admin', 1, NULL, NULL), "
                "(2, 'faculty@example.com', 'F', 'faculty', 1, NULL, NULL), "
                "(3, 't004@siu', 'T', 'faculty', 2, 'sub-3', 'T004')"
            )
            c.exec_driver_sql(
                "INSERT INTO approver_assignments (id, user_id, title, scope_level, organization_id, "
                "institute_id, department_id) VALUES (1, 3, 'HOD', 'department', 2, 2, 3)"
            )

        _alembic(environment, "upgrade", REVISION)
        assert "sync_state" in inspect(engine).get_table_names()
        assert {"eklink_id", "source"} <= _columns(engine, "approver_assignments")
        with engine.connect() as c:
            assert c.exec_driver_sql(
                "SELECT id, code, is_demo FROM organizations ORDER BY id"
            ).fetchall() == [(1, "DEMO", 1), (2, "SIU", 0)]
            assert c.exec_driver_sql(
                "SELECT id, name, code, is_demo FROM institutes ORDER BY id"
            ).fetchall() == [(1, "TemplateOS Demo Institute", "DEMO-INST", 1), (2, "SIT", "SIT", 0)]
            assert c.exec_driver_sql(
                "SELECT id, code, is_demo FROM departments ORDER BY id"
            ).fetchall() == [(1, "ACAD", 1), (2, "CS", 1), (3, "CSE", 0)]
            assert c.exec_driver_sql("SELECT id, is_demo FROM users ORDER BY id").fetchall() == [
                (1, 1), (2, 1), (3, 0)
            ]
            assert c.exec_driver_sql(
                "SELECT eklink_id, source FROM approver_assignments"
            ).fetchall() == [(None, "local")]
        assert "uq_organizations_name_lower" in _indexes(engine, "organizations")
        assert "uq_departments_institute_name_lower" in _indexes(engine, "departments")
        assert "uq_approver_assignments_eklink_id" in _indexes(engine, "approver_assignments")

        _alembic(environment, "downgrade", PREVIOUS)
        assert "sync_state" not in inspect(engine).get_table_names()
        assert "is_demo" not in _columns(engine, "users")
        assert "is_demo" not in _columns(engine, "departments")
        assert "eklink_id" not in _columns(engine, "approver_assignments")
        with engine.connect() as c:
            assert c.exec_driver_sql("SELECT code FROM organizations ORDER BY id").fetchall() == [
                (None,), ("SIU",)
            ]
            assert c.exec_driver_sql("SELECT code FROM institutes ORDER BY id").fetchall() == [
                ("MAIN",), ("SIT",)
            ]
            assert c.exec_driver_sql("SELECT code FROM departments ORDER BY id").fetchall() == [
                (None,), (None,), ("CSE",)
            ]
            assert c.exec_driver_sql("SELECT count(*) FROM users").scalar() == 3
            assert c.exec_driver_sql("SELECT count(*) FROM approver_assignments").scalar() == 1
        assert "uq_organizations_name_lower" in _indexes(engine, "organizations")
        assert "uq_institutes_org_name_lower" in _indexes(engine, "institutes")
        assert "uq_departments_institute_name_lower" in _indexes(engine, "departments")
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
    # Later revisions build on this one; there must still be a single head.
    assert heads.count("(head)") == 1
