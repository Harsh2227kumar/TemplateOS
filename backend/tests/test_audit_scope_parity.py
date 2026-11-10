"""
audit_scope_filter (SQL) and row_visible_to (Python) agree for every viewer
x row combination, and can_view_audit matches who sees anything at all.
"""

import os

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

import app.models  # noqa: F401,E402
from app.db.base import Base  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.organization import Department, Organization  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.audit_scope import audit_scope_filter, can_view_audit, row_visible_to  # noqa: E402

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_sql_filter_matches_python_twin():
    with TestSession() as db:
        org_a, org_b = Organization(name="A"), Organization(name="B")
        db.add_all([org_a, org_b])
        db.flush()
        dept_a1 = Department(organization_id=org_a.id, name="A1")
        dept_a2 = Department(organization_id=org_a.id, name="A2")
        dept_b1 = Department(organization_id=org_b.id, name="B1")
        db.add_all([dept_a1, dept_a2, dept_b1])
        db.flush()

        scopes = [
            (None, None), (org_a.id, None), (org_a.id, dept_a1.id), (org_a.id, dept_a2.id),
            (org_b.id, None), (org_b.id, dept_b1.id), (None, dept_a1.id),
        ]
        for index in range(12):
            org_id, dept_id = scopes[index % len(scopes)]
            db.add(AuditLog(action="auth.login", entity_type="user", summary=f"row {index}",
                            organization_id=org_id, department_id=dept_id))
        db.commit()
        rows = db.scalars(select(AuditLog).order_by(AuditLog.id)).all()

        viewers = [
            User(email="s@x", full_name="S", role="super_admin"),
            User(email="o@x", full_name="O", role="org_admin", organization_id=org_a.id),
            User(email="o2@x", full_name="O2", role="org_admin"),  # no organization
            User(email="d@x", full_name="D", role="department_admin", organization_id=org_a.id,
                 department_id=dept_a1.id),
            User(email="d2@x", full_name="D2", role="department_admin", organization_id=org_b.id),  # no dept
            User(email="f@x", full_name="F", role="faculty", organization_id=org_a.id, department_id=dept_a1.id),
        ]
        expected_counts = {"s@x": 12, "o@x": 6, "o2@x": 0, "d@x": 3, "d2@x": 0, "f@x": 0}
        for viewer in viewers:
            clause = audit_scope_filter(viewer)
            statement = select(AuditLog.id).order_by(AuditLog.id)
            if clause is not None:
                statement = statement.where(clause)
            sql_ids = list(db.scalars(statement))
            python_ids = [row.id for row in rows if row_visible_to(viewer, row)]
            assert sql_ids == python_ids, viewer.email
            assert len(sql_ids) == expected_counts[viewer.email], viewer.email
            assert can_view_audit(viewer) == (viewer.email in {"s@x", "o@x", "d@x"})
