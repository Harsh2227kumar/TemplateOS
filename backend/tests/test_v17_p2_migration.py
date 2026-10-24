"""
Migration a7d3f9c1e5b8 (V1.7 P2: document versions, rich text, AI flags) on
a throwaway SQLite file, with data:

- upgrade from e3c9a7b5d1f2 backfills every generated_files row as version 1
  of its document with a snapshot of the current values
- new columns / defaults / constraints exist
- several versions per document can then be stored
- downgrade keeps the newest row per document and restores the 1:1 shape
- upgrading again works and backfills again
"""

import json
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
PREVIOUS_REVISION = "e3c9a7b5d1f2"
REVISION = "a7d3f9c1e5b8"
VALUE_COLUMNS = {"value_format", "rich_content", "ai_modified", "ai_action", "ai_modified_at"}


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
    db_file = tmp_path / "versions.db"
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return db_file, environment


def _seed_v16(db_file: Path) -> None:
    """Two generated documents (V1.6 shape) and one draft."""
    with sqlite3.connect(db_file) as connection:
        connection.executescript(
            """
            INSERT INTO users (id, email, full_name, role) VALUES (1, 'a@x', 'A', 'faculty');
            INSERT INTO templates (id, name, category, visibility, status, uploaded_by)
                VALUES (1, 'T', 'notice', 'public', 'active', 1);
            INSERT INTO documents (id, template_id, created_by, name, status) VALUES
                (1, 1, 1, 'D1', 'generated'), (2, 1, 1, 'D2', 'generated'), (3, 1, 1, 'D3', 'draft');
            INSERT INTO document_values (document_id, field_name, value) VALUES
                (1, 'venue', 'Hall & "B"'), (1, 'agenda', '["a", "b"]'),
                (2, 'title', 'Second'), (3, 'title', 'Draft only');
            INSERT INTO generated_files
                (id, document_id, docx_path, pdf_path, template_version, generated_at, pdf_status)
            VALUES
                (10, 1, 'generated/docx/d1.docx', 'generated/pdf/d1.pdf', 3, '2026-10-01 10:00:00', 'converted'),
                (11, 2, 'generated/docx/d2.docx', NULL, 1, '2026-10-02 11:00:00', 'failed');
            """
        )


def _query(db_file: Path, sql: str) -> list[tuple]:
    with sqlite3.connect(db_file) as connection:
        return connection.execute(sql).fetchall()


def test_upgrade_backfills_versions_and_round_trips(migration_db) -> None:
    db_file, environment = migration_db
    _alembic(environment, "upgrade", PREVIOUS_REVISION)
    _seed_v16(db_file)

    _alembic(environment, "upgrade", REVISION)

    versions = _query(
        db_file,
        "SELECT document_id, version, created_by, created_at, template_version, values_snapshot "
        "FROM document_versions ORDER BY document_id",
    )
    assert [row[:5] for row in versions] == [
        (1, 1, 1, "2026-10-01 10:00:00", 3),
        (2, 1, 1, "2026-10-02 11:00:00", 1),
    ]
    snapshot = json.loads(versions[0][5])
    assert snapshot == [
        {"field_name": "agenda", "value": '["a", "b"]', "value_format": "plain",
         "rich_content": None, "ai_modified": False, "ai_action": None},
        {"field_name": "venue", "value": 'Hall & "B"', "value_format": "plain",
         "rich_content": None, "ai_modified": False, "ai_action": None},
    ]
    assert json.loads(versions[1][5])[0]["value"] == "Second"

    files = _query(
        db_file,
        "SELECT gf.id, gf.document_id, dv.version, gf.files_pruned_at FROM generated_files gf "
        "JOIN document_versions dv ON dv.id = gf.version_id ORDER BY gf.id",
    )
    assert files == [(10, 1, 1, None), (11, 2, 1, None)]

    values = _query(
        db_file,
        "SELECT value_format, rich_content, ai_modified, ai_action, ai_modified_at "
        "FROM document_values ORDER BY id",
    )
    assert set(values) == {("plain", None, 0, None, None)}

    engine = create_engine(environment["DATABASE_URL"])
    try:
        inspector = inspect(engine)
        value_columns = {c["name"]: c for c in inspector.get_columns("document_values")}
        assert VALUE_COLUMNS <= set(value_columns)
        assert value_columns["value_format"]["nullable"] is False
        assert value_columns["ai_modified"]["nullable"] is False
        gf_columns = {c["name"]: c for c in inspector.get_columns("generated_files")}
        assert gf_columns["version_id"]["nullable"] is False
        unique = {
            tuple(c["column_names"]) for c in inspector.get_unique_constraints("generated_files")
        }
        assert ("version_id",) in unique
        assert ("document_id",) not in unique
        foreign = {
            fk["referred_table"]: fk for fk in inspector.get_foreign_keys("generated_files")
        }
        assert foreign["document_versions"]["options"].get("ondelete") == "CASCADE"
        version_unique = {
            tuple(c["column_names"]) for c in inspector.get_unique_constraints("document_versions")
        }
        assert ("document_id", "version") in version_unique
    finally:
        engine.dispose()

    # The CHECK constraint and new defaults work.
    with sqlite3.connect(db_file) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO document_values (document_id, field_name, value, value_format) "
                "VALUES (3, 'bad', 'x', 'html')"
            )
        connection.execute(
            "INSERT INTO document_values (document_id, field_name, value) VALUES (3, 'ok', 'x')"
        )
        assert connection.execute(
            "SELECT value_format, ai_modified FROM document_values WHERE field_name = 'ok'"
        ).fetchone() == ("plain", 0)
        # A second and third version for document 1 (several rows per document).
        for number, gf_id in ((2, 12), (3, 13)):
            connection.execute(
                "INSERT INTO document_versions (document_id, version, values_snapshot) "
                "VALUES (1, ?, '[]')",
                (number,),
            )
            version_id = connection.execute(
                "SELECT id FROM document_versions WHERE document_id = 1 AND version = ?",
                (number,),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO generated_files (id, document_id, version_id, docx_path) "
                "VALUES (?, 1, ?, ?)",
                (gf_id, version_id, f"generated/docx/d1-v{number}.docx"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO document_versions (document_id, version, values_snapshot) "
                "VALUES (1, 3, '[]')"
            )

    _alembic(environment, "downgrade", PREVIOUS_REVISION)
    engine = create_engine(environment["DATABASE_URL"])
    try:
        inspector = inspect(engine)
        assert "document_versions" not in inspector.get_table_names()
        assert not VALUE_COLUMNS & {c["name"] for c in inspector.get_columns("document_values")}
        gf_columns = {c["name"] for c in inspector.get_columns("generated_files")}
        assert not {"version_id", "files_pruned_at"} & gf_columns
        unique = {
            tuple(c["column_names"]) for c in inspector.get_unique_constraints("generated_files")
        }
        assert ("document_id",) in unique
    finally:
        engine.dispose()
    # The newest version's row survives per document.
    assert _query(db_file, "SELECT id, document_id, docx_path FROM generated_files ORDER BY id") == [
        (11, 2, "generated/docx/d2.docx"),
        (13, 1, "generated/docx/d1-v3.docx"),
    ]

    _alembic(environment, "upgrade", "head")
    assert _query(
        db_file,
        "SELECT gf.id, dv.document_id, dv.version FROM generated_files gf "
        "JOIN document_versions dv ON dv.id = gf.version_id ORDER BY gf.id",
    ) == [(11, 2, 1), (13, 1, 1)]


def test_upgrade_on_empty_database(migration_db) -> None:
    db_file, environment = migration_db
    _alembic(environment, "upgrade", "head")
    assert _query(db_file, "SELECT COUNT(*) FROM document_versions") == [(0,)]
    _alembic(environment, "downgrade", PREVIOUS_REVISION)
    _alembic(environment, "upgrade", "head")


def test_single_head() -> None:
    environment = {
        **os.environ,
        "DATABASE_URL": "sqlite://",
        "JWT_SECRET_KEY": "test-secret-that-is-long-enough-for-migration-tests",
    }
    heads = _alembic(environment, "heads").stdout.split()
    assert len(heads) >= 2  # "<rev> (head)": newer revisions follow this one
    assert heads.count("(head)") == 1
