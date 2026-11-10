"""
Migration d2f9b4e7c1a8 repairs documents / document_values tables created by
the uncommitted f3713a976f21 migration (found on the shared Neon database):
RESTRICT / missing ON DELETE on the documents FKs, no unique
(document_id, field_name), documents.status VARCHAR(30).

1. Drifted DB: reproduce that schema, stamp 9a8b7c6d5e4f (the recovery
   step), upgrade head -> constraints match the repo, data survives, and
   deleting a template cascades.
2. Clean DB: upgrade head from scratch -> the repair is a no-op.
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, event, inspect

BACKEND_DIR = Path(__file__).resolve().parents[1]

# One line per constraint: SQLAlchemy reads SQLite FK options from the DDL text.
DRIFTED_DOCUMENTS_DDL = """
CREATE TABLE documents (
    id INTEGER NOT NULL PRIMARY KEY,
    template_id INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    name VARCHAR(255),
    status VARCHAR(30) DEFAULT 'draft' NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT documents_template_id_fkey FOREIGN KEY(template_id) REFERENCES templates (id) ON DELETE RESTRICT,
    CONSTRAINT documents_created_by_fkey FOREIGN KEY(created_by) REFERENCES users (id)
)
"""

DRIFTED_DOCUMENT_VALUES_DDL = """
CREATE TABLE document_values (
    id INTEGER NOT NULL PRIMARY KEY,
    document_id INTEGER NOT NULL,
    field_name VARCHAR(100) NOT NULL,
    value TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT document_values_document_id_fkey FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
)
"""


def _alembic(environment: dict, *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini.example", *args],
        cwd=BACKEND_DIR,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def _environment(tmp_path: Path, name: str) -> dict:
    return {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{(tmp_path / name).as_posix()}",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
    }


def _assert_documents_schema_matches_repo(engine) -> None:
    inspector = inspect(engine)
    document_fks = {
        fk["constrained_columns"][0]: fk for fk in inspector.get_foreign_keys("documents")
    }
    assert document_fks["template_id"]["referred_table"] == "templates"
    assert document_fks["template_id"]["options"].get("ondelete") == "CASCADE"
    assert document_fks["created_by"]["referred_table"] == "users"
    assert document_fks["created_by"]["options"].get("ondelete") == "CASCADE"
    assert len(document_fks) == 2

    value_fks = inspector.get_foreign_keys("document_values")
    assert [fk["options"].get("ondelete") for fk in value_fks] == ["CASCADE"]

    uniques = inspector.get_unique_constraints("document_values")
    assert any(set(u["column_names"]) == {"document_id", "field_name"} for u in uniques)

    status = next(c for c in inspector.get_columns("documents") if c["name"] == "status")
    assert status["type"].length == 50

    # The V1.5 FK from c4d8e2f6a1b3 is applied on top.
    assert any(
        fk["referred_table"] == "documents"
        for fk in inspector.get_foreign_keys("ai_generations")
    )


def test_repair_migration_fixes_drifted_documents_tables(tmp_path: Path) -> None:
    environment = _environment(tmp_path, "drifted.db")

    # The shared DB was at ai_generations, then f3713a976f21 created these.
    _alembic(environment, "upgrade", "e5f2a8c6d4b7")
    engine = create_engine(environment["DATABASE_URL"])
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(DRIFTED_DOCUMENTS_DDL)
            connection.exec_driver_sql(DRIFTED_DOCUMENT_VALUES_DDL)
            connection.exec_driver_sql(
                "INSERT INTO users (email, full_name, role) "
                "VALUES ('drift@example.com', 'Drift Owner', 'normal_user')"
            )
            connection.exec_driver_sql(
                "INSERT INTO templates (name, category, visibility, status, uploaded_by) "
                "VALUES ('Drift Template', 'mom', 'private', 'active', 1)"
            )
            connection.exec_driver_sql(
                "INSERT INTO documents (template_id, created_by, name) VALUES (1, 1, 'Draft')"
            )
            connection.exec_driver_sql(
                "INSERT INTO document_values (document_id, field_name, value) "
                "VALUES (1, 'title', 'Kept'), (1, 'summary', 'Also kept')"
            )
    finally:
        engine.dispose()

    # Recovery steps.
    _alembic(environment, "stamp", "9a8b7c6d5e4f")
    _alembic(environment, "upgrade", "head")

    engine = create_engine(environment["DATABASE_URL"])

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    try:
        _assert_documents_schema_matches_repo(engine)

        with engine.begin() as connection:
            assert connection.exec_driver_sql("SELECT name FROM documents").scalar_one() == "Draft"
            assert connection.exec_driver_sql(
                "SELECT count(*) FROM document_values"
            ).scalar_one() == 2

            # RESTRICT is gone: deleting the template cascades to its drafts.
            connection.exec_driver_sql("DELETE FROM templates WHERE id = 1")
            assert connection.exec_driver_sql("SELECT count(*) FROM documents").scalar_one() == 0
            assert connection.exec_driver_sql(
                "SELECT count(*) FROM document_values"
            ).scalar_one() == 0
    finally:
        engine.dispose()


def test_repair_migration_is_noop_on_clean_database(tmp_path: Path) -> None:
    environment = _environment(tmp_path, "clean.db")
    _alembic(environment, "upgrade", "head")

    engine = create_engine(environment["DATABASE_URL"])
    try:
        _assert_documents_schema_matches_repo(engine)
        # Exactly the constraint 9a8b7c6d5e4f created; no duplicate added.
        uniques = inspect(engine).get_unique_constraints("document_values")
        assert [u["name"] for u in uniques] == ["uq_document_value_key"]
    finally:
        engine.dispose()

    # Downgrade past the repair and back up again stays clean.
    _alembic(environment, "downgrade", "c4d8e2f6a1b3")
    _alembic(environment, "upgrade", "head")
