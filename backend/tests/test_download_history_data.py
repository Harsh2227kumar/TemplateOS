"""
V1.7 Phase 3 data layer: download history.

- record_download snapshots name / version / version_source and clips the user agent.
- History survives deleting the version, the document and the user (SET NULL).
- list_user_downloads: own rows only, format / document filters, pagination totals.
- list_document_downloads: newest first.
- DownloadHistoryItem.document_exists.

Database: in-memory SQLite with PRAGMA foreign_keys=ON.
"""

import os
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

import app.models  # noqa: F401,E402
from app.core.clock import utc_now_naive  # noqa: E402
from app.crud.download_history_crud import (  # noqa: E402
    list_document_downloads,
    list_user_downloads,
    record_download,
)
from app.db.base import Base  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.document_version import DocumentVersion  # noqa: E402
from app.models.download_history import DownloadHistory  # noqa: E402
from app.models.template import Template  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.audit import DownloadHistoryItem  # noqa: E402

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


def _setup(db, email="owner@x.test"):
    uploader = User(email=f"admin-{email}", full_name="Admin", role="org_admin")
    user = User(email=email, full_name="Owner", role="faculty")
    db.add_all([uploader, user])
    db.flush()
    template = Template(name="MoM", category="mom", visibility="public", status="active", uploaded_by=uploader.id)
    db.add(template)
    db.flush()
    document = Document(template_id=template.id, created_by=user.id, name="Budget meeting", status="generated")
    db.add(document)
    db.flush()
    v1 = DocumentVersion(document_id=document.id, version=1, values_snapshot="[]")
    v2 = DocumentVersion(document_id=document.id, version=2, values_snapshot="[]", source="manual_edit", base_version=v1)
    db.add_all([v1, v2])
    db.flush()
    return user, document, v1, v2


def test_record_snapshots_and_survives_deletes():
    with TestSession() as db:
        user, document, _v1, v2 = _setup(db)
        row = record_download(
            db, user=user, document=document, version=v2, fmt="docx", file_name="budget-meeting.docx",
            file_size=1234, ip="127.0.0.1", user_agent="x" * 400,
        )
        db.commit()
        assert (row.document_name, row.version, row.version_source, row.format) == (
            "Budget meeting", 2, "manual_edit", "docx"
        )
        assert len(row.user_agent) == 255

        db.delete(v2)
        db.commit()
        db.delete(document)
        db.commit()
        db.delete(user)
        db.commit()
        kept = db.scalars(select(DownloadHistory)).one()
        assert (kept.user_id, kept.document_id, kept.version_id) == (None, None, None)
        assert (kept.document_name, kept.version, kept.version_source, kept.file_size) == (
            "Budget meeting", 2, "manual_edit", 1234
        )
        assert DownloadHistoryItem.model_validate(kept).document_exists is False


def test_unnamed_document_and_bad_format():
    with TestSession() as db:
        user, document, v1, _v2 = _setup(db)
        document.name = None
        row = record_download(db, user=user, document=document, version=None, fmt="pdf", file_name="d.pdf",
                              file_size=None, ip=None, user_agent=None)
        assert row.document_name == f"Document {document.id}" and row.version is None
        with pytest.raises(ValueError):
            record_download(db, user=user, document=document, version=v1, fmt="xlsx", file_name="d.xlsx",
                            file_size=None, ip=None, user_agent=None)


def test_user_and_document_listings():
    with TestSession() as db:
        user, document, v1, v2 = _setup(db)
        other = User(email="other@x.test", full_name="Other", role="faculty")
        db.add(other)
        db.flush()
        start = utc_now_naive()
        for index, (who, version, fmt) in enumerate(
            [(user, v1, "docx"), (user, v1, "pdf"), (user, v2, "pdf"), (other, v2, "pdf")]
        ):
            row = record_download(db, user=who, document=document, version=version, fmt=fmt,
                                  file_name=f"f{index}.{fmt}", file_size=index, ip=None, user_agent=None)
            row.downloaded_at = start + timedelta(minutes=index)
        db.commit()

        rows, total = list_user_downloads(db, user.id, page=1, limit=2)
        assert total == 3 and [r.file_name for r in rows] == ["f2.pdf", "f1.pdf"]
        rows, total = list_user_downloads(db, user.id, page=2, limit=2)
        assert total == 3 and [r.file_name for r in rows] == ["f0.docx"]
        rows, total = list_user_downloads(db, user.id, fmt="pdf")
        assert total == 2
        rows, total = list_user_downloads(db, user.id, document_id=document.id + 1)
        assert total == 0 and rows == []

        rows, total = list_document_downloads(db, document.id, limit=10)
        assert total == 4 and rows[0].file_name == "f3.pdf"
        item = DownloadHistoryItem.model_validate(rows[0])
        assert item.document_exists is True and item.version_source == "manual_edit"
