"""
Migration c7a1d3e5f9b2 (organizations / departments tables) on a throwaway
SQLite file: upgrade from f1b7c3d9e2a4 backfills the tables from messy
free-text values, downgrade drops them again without touching the legacy
strings, and upgrading again works.
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-migration-tests")

BACKEND_DIR = Path(__file__).resolve().parents[1]
PREVIOUS = "f1b7c3d9e2a4"


def _alembic(environment: dict, *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini.example", *args],
        cwd=BACKEND_DIR,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def _columns(engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


def _seed(engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, full_name, role, organization, department) VALUES "
            "(1, 'u1@x', 'U1', 'faculty', ' State University ', 'Computer Science'), "
            "(2, 'u2@x', 'U2', 'student', 'state university', 'computer   science'), "
            "(3, 'u3@x', 'U3', 'faculty', 'State University', 'Mechanical'), "
            "(4, 'u4@x', 'U4', 'org_admin', 'STATE UNIVERSITY', NULL), "
            "(5, 'u5@x', 'U5', 'student', NULL, 'Orphan Dept'), "
            "(6, 'u6@x', 'U6', 'normal_user', '', '  '), "
            "(7, 'u7@x', 'U7', 'faculty', 'Other College', 'Computer Science'), "
            "(8, 'u8@x', 'U8', 'faculty', 'State University', 'Computer Science')"
        )
        connection.exec_driver_sql(
            "INSERT INTO templates (id, name, category, visibility, status, uploaded_by, "
            "scope_organization, scope_department) VALUES "
            "(1, 'Letterhead', 'letter', 'organization', 'active', 4, 'State University', NULL), "
            "(2, 'CS form', 'notice', 'department', 'active', 1, 'state university', "
            "'COMPUTER SCIENCE'), "
            "(3, 'Orphan', 'notice', 'department', 'active', 5, NULL, 'Physics'), "
            "(4, 'Public', 'notice', 'public', 'active', 1, NULL, NULL)"
        )


def _assert_backfilled(engine) -> None:
    with engine.connect() as connection:
        organizations = dict(
            connection.exec_driver_sql("SELECT name, id FROM organizations").all()
        )
        assert set(organizations) == {"State University", "Other College"}
        su, oc = organizations["State University"], organizations["Other College"]

        departments = {
            (row[1], row[2]): row[0]
            for row in connection.exec_driver_sql(
                "SELECT id, organization_id, name FROM departments"
            ).all()
        }
        # Most common spelling wins; whitespace collapsed; one row per org.
        assert set(departments) == {
            (su, "Computer Science"),
            (su, "Mechanical"),
            (oc, "Computer Science"),
        }
        su_cs = departments[(su, "Computer Science")]
        su_me = departments[(su, "Mechanical")]
        oc_cs = departments[(oc, "Computer Science")]

        users = [
            tuple(row)
            for row in connection.exec_driver_sql(
                "SELECT id, organization_id, department_id, organization, department "
                "FROM users ORDER BY id"
            ).all()
        ]
        assert users == [
            (1, su, su_cs, " State University ", "Computer Science"),
            (2, su, su_cs, "state university", "computer   science"),
            (3, su, su_me, "State University", "Mechanical"),
            (4, su, None, "STATE UNIVERSITY", None),
            # Department without organization: unlinked, legacy string kept.
            (5, None, None, None, "Orphan Dept"),
            (6, None, None, "", "  "),
            (7, oc, oc_cs, "Other College", "Computer Science"),
            (8, su, su_cs, "State University", "Computer Science"),
        ]

        templates = [
            tuple(row)
            for row in connection.exec_driver_sql(
                "SELECT id, scope_organization_id, scope_department_id, scope_department "
                "FROM templates ORDER BY id"
            ).all()
        ]
        assert templates == [
            (1, su, None, None),
            (2, su, su_cs, "COMPUTER SCIENCE"),
            (3, None, None, "Physics"),
            (4, None, None, None),
        ]


def test_org_tables_migration_up_down_up(tmp_path: Path) -> None:
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'orgs.db').as_posix()}",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
    }
    _alembic(environment, "upgrade", PREVIOUS)
    engine = create_engine(environment["DATABASE_URL"])
    try:
        assert "organizations" not in inspect(engine).get_table_names()
        _seed(engine)
    finally:
        engine.dispose()

    _alembic(environment, "upgrade", "head")
    engine = create_engine(environment["DATABASE_URL"])
    try:
        assert {"organizations", "departments"} <= set(inspect(engine).get_table_names())
        assert {"organization_id", "department_id"} <= _columns(engine, "users")
        assert {"scope_organization_id", "scope_department_id"} <= _columns(
            engine, "templates"
        )
        fks = {
            fk["constrained_columns"][0]: fk
            for fk in inspect(engine).get_foreign_keys("users")
        }
        assert fks["organization_id"]["referred_table"] == "organizations"
        assert fks["organization_id"]["options"].get("ondelete") == "SET NULL"
        assert fks["department_id"]["referred_table"] == "departments"
        _assert_backfilled(engine)
    finally:
        engine.dispose()

    _alembic(environment, "downgrade", PREVIOUS)
    engine = create_engine(environment["DATABASE_URL"])
    try:
        tables = set(inspect(engine).get_table_names())
        assert not {"organizations", "departments"} & tables
        assert not {"organization_id", "department_id"} & _columns(engine, "users")
        assert not {"scope_organization_id", "scope_department_id"} & _columns(
            engine, "templates"
        )
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM users").scalar_one() == 8
            assert (
                connection.exec_driver_sql(
                    "SELECT department FROM users WHERE id = 2"
                ).scalar_one()
                == "computer   science"
            )
    finally:
        engine.dispose()

    _alembic(environment, "upgrade", "head")
    engine = create_engine(environment["DATABASE_URL"])
    try:
        _assert_backfilled(engine)
    finally:
        engine.dispose()
