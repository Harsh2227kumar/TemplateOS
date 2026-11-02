"""
V1.7 Phase 3 data layer: audit logs.

- Catalog: every planned action (incl. the P2.1 editor actions) with a label and a known area.
- add_audit_log: unknown action / entity rejected, actor email snapshot, failed login without an
  actor, callback events without an IP, details JSON capped at 4 KB, summary clipped.
- Deleting the actor keeps the row (actor_id NULL, email kept).
- search_audit_logs: filters, LIKE escaping, date range, pagination totals under scoping.
- iter_audit_logs_for_export: same scope, max rows.
- AuditLogItem parses details.
- prune: dry run counts, --yes deletes only old rows.

Database: in-memory SQLite with PRAGMA foreign_keys=ON.
"""

import json
import os
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

import app.models  # noqa: F401,E402
from app.core.clock import utc_now_naive  # noqa: E402
from app.crud.audit_log_crud import (  # noqa: E402
    DETAILS_MAX_BYTES,
    AuditFilters,
    add_audit_log,
    iter_audit_logs_for_export,
    search_audit_logs,
)
from app.db.base import Base  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.download_history import DownloadHistory  # noqa: E402
from app.models.organization import Department, Organization  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.audit import AuditLogItem  # noqa: E402
from app.services.audit_catalog import AUDIT_ACTIONS, AUDIT_AREAS, action_options, is_known_action  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prune_audit_logs import prune  # noqa: E402

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _org(db):
    org = Organization(name="SIT")
    db.add(org)
    db.flush()
    dept = Department(organization_id=org.id, name="CSE")
    db.add(dept)
    db.flush()
    return org, dept


def test_catalog_covers_the_plan():
    planned = {
        "template.upload", "template.access_update", "template.delete", "template.placeholders_detect",
        "template.placeholders_fix", "template.clean", "template.fields_update", "template.customize",
        "template.file_edit", "template.revision_restore", "document.create", "document.values_update",
        "document.generate", "document.pdf_retry", "document.version_restore", "document.download",
        "document.file_edit", "editor.session_open", "editor.save_failed", "ai.improve_text",
        "ai.suggest_fields", "admin.user_update", "admin.organization_create", "admin.organization_update",
        "admin.organization_delete", "admin.department_create", "admin.department_update",
        "admin.department_delete", "admin.audit_export", "auth.login", "auth.logout", "auth.login_failed",
    }
    assert planned <= set(AUDIT_ACTIONS)
    assert all(label and area in AUDIT_AREAS for label, area in AUDIT_ACTIONS.values())
    assert is_known_action("editor.session_open") and not is_known_action("document.teleport")
    options = action_options()
    assert options[0] == {"action": "template.upload", "label": "Template uploaded", "area": "templates"}
    assert len(options) == len(AUDIT_ACTIONS)


def test_add_audit_log_rules():
    with TestSession() as db:
        org, dept = _org(db)
        actor = User(email="priya@x.test", full_name="Priya", role="faculty")
        db.add(actor)
        db.flush()
        with pytest.raises(ValueError):
            add_audit_log(db, actor=actor, action="document.teleport", entity_type="document", summary="x")
        with pytest.raises(ValueError):
            add_audit_log(db, actor=actor, action="document.create", entity_type="spaceship", summary="x")

        row = add_audit_log(
            db, actor=actor, action="document.create", entity_type="document", entity_id=7,
            summary="Created 'Budget' " + "x" * 600, details={"template_id": 3},
            organization_id=org.id, department_id=dept.id, ip="10.0.0.1",
        )
        assert row.actor_email == "priya@x.test" and len(row.summary) == 500
        assert json.loads(row.details) == {"template_id": 3}

        failed = add_audit_log(db, actor=None, action="auth.login_failed", entity_type="user",
                               summary="Failed login", actor_email="who@x.test", ip="10.0.0.2")
        assert (failed.actor_id, failed.actor_email) == (None, "who@x.test")

        callback = add_audit_log(db, actor=actor, action="template.file_edit", entity_type="template",
                                 entity_id=1, summary="Edited", details={"revision": 2}, ip=None)
        assert callback.ip_address is None

        big = add_audit_log(db, actor=actor, action="template.fields_update", entity_type="template",
                            summary="Fields", details={"names": ["f" * 100] * 100, "count": 100})
        assert len(big.details.encode()) <= DETAILS_MAX_BYTES
        assert json.loads(big.details) == {"_truncated": True, "keys": ["count", "names"]}
        assert add_audit_log(db, actor=actor, action="auth.logout", entity_type="user", summary="Out").details is None
        db.commit()

        db.delete(actor)
        db.commit()
        kept = db.scalars(select(AuditLog).where(AuditLog.action == "document.create")).one()
        assert (kept.actor_id, kept.actor_email) == (None, "priya@x.test")
        item = AuditLogItem.model_validate(kept)
        assert item.details == {"template_id": 3}


def _seed_rows(db):
    org, dept = _org(db)
    other_org = Organization(name="Other")
    db.add(other_org)
    db.flush()
    actor = User(email="a@x.test", full_name="A", role="faculty", organization_id=org.id, department_id=dept.id)
    db.add(actor)
    db.flush()
    start = utc_now_naive() - timedelta(days=10)
    specs = [
        ("document.download", "Downloaded PDF of '100%_done'", org.id, dept.id),
        ("document.download", "Downloaded DOCX of 'Budget'", org.id, None),
        ("template.upload", "Uploaded 'MoM'", org.id, dept.id),
        ("template.upload", "Uploaded 'Other MoM'", other_org.id, None),
        ("auth.login", "Signed in", None, None),
    ]
    for index, (action, summary, org_id, dept_id) in enumerate(specs):
        row = add_audit_log(db, actor=actor, action=action, entity_type="document", entity_id=index,
                            summary=summary, organization_id=org_id, department_id=dept_id)
        row.created_at = start + timedelta(days=index)
    db.commit()
    return org, dept, actor, start


def test_search_filters_scope_and_pagination():
    with TestSession() as db:
        org, dept, actor, start = _seed_rows(db)
        super_admin = User(email="s@x.test", full_name="S", role="super_admin")
        org_admin = User(email="o@x.test", full_name="O", role="org_admin", organization_id=org.id)
        dept_admin = User(email="d@x.test", full_name="D", role="department_admin",
                          organization_id=org.id, department_id=dept.id)
        faculty = User(email="f@x.test", full_name="F", role="faculty", organization_id=org.id)

        rows, total = search_audit_logs(db, viewer=super_admin, page=1, limit=2)
        assert total == 5 and [r.entity_id for r in rows] == [4, 3]
        assert search_audit_logs(db, viewer=org_admin)[1] == 3
        rows, total = search_audit_logs(db, viewer=org_admin, page=2, limit=2)
        assert total == 3 and [r.entity_id for r in rows] == [0]
        assert search_audit_logs(db, viewer=dept_admin)[1] == 2
        assert search_audit_logs(db, viewer=faculty) == ([], 0)

        by = lambda **kw: search_audit_logs(db, viewer=super_admin, filters=AuditFilters(**kw))[1]  # noqa: E731
        assert by(action="template.upload") == 2
        assert by(actor_id=actor.id) == 5
        assert by(entity_type="document", entity_id=2) == 1
        assert by(q="100%") == 1          # % matches literally
        assert by(q="100%_D") == 1        # _ matches literally
        assert by(q="BUDGET") == 1        # case-insensitive
        assert by(q="a@x.test") == 5      # actor email
        assert by(date_from=start + timedelta(days=1), date_to=start + timedelta(days=3)) == 2

        exported = list(iter_audit_logs_for_export(db, viewer=org_admin, max_rows=2))
        assert [r.entity_id for r in exported] == [2, 1]
        assert list(iter_audit_logs_for_export(db, viewer=faculty)) == []


def test_prune_dry_run_and_delete():
    with TestSession() as db:
        actor = User(email="a@x.test", full_name="A", role="faculty")
        db.add(actor)
        db.flush()
        now = utc_now_naive()
        for days in (400, 10):
            row = add_audit_log(db, actor=actor, action="auth.login", entity_type="user", summary="in")
            row.created_at = now - timedelta(days=days)
        for days in (800, 10):
            db.add(DownloadHistory(user_id=actor.id, format="pdf", document_name="D", file_name="d.pdf",
                                   downloaded_at=now - timedelta(days=days)))
        db.commit()

        result = prune(db, now=now, audit_days=365, download_days=730, dry_run=True)
        assert (result.audit_logs, result.download_history) == (1, 1)
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 2

        result = prune(db, now=now, audit_days=365, download_days=730, dry_run=False)
        assert (result.audit_logs, result.download_history) == (1, 1)
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 1
        assert db.scalar(select(func.count()).select_from(DownloadHistory)) == 1
