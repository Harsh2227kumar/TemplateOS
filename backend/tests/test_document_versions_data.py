"""
V1.7 Phase 2 data layer (Member 3): rich values, AI flags, document versions.

Coverage:
- DocumentValue: value_format / ai_action validators, defaults.
- upsert_values: rich content stored as JSON text, plain clears it,
  ai_modified_at set when the flag flips, kept while unchanged, cleared.
- snapshot_values / parse_snapshot / dump_snapshot shape.
- create_version numbering, retry once on a duplicate number.
- list / get / count versions; Document.versions order.
- latest output: Document.generated_file, latest_generated_file,
  get_generated_files_for_documents.
- diff_snapshots / changed_fields_by_version.
- restore_values: snapshot applied, absent fields deleted, flags restored.
- prune_old_version_files: keeps the newest N, returns paths, idempotent.
- Cascades: document delete removes versions, rows and stored files;
  version creator delete -> created_by NULL.
- Schemas: DocumentValueRead parses rich_content, version schemas.

Database: in-memory SQLite with PRAGMA foreign_keys=ON.
"""

import json
import os
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

import app.models  # noqa: F401,E402  (register every mapper)
from app.core.config import Settings, settings  # noqa: E402
from app.crud import document_version_crud as versions_crud  # noqa: E402
from app.crud.document_crud import delete_document  # noqa: E402
from app.crud.document_value_crud import upsert_values  # noqa: E402
from app.crud.generated_file_crud import (  # noqa: E402
    create_generated_file,
    get_generated_files_for_documents,
    latest_generated_file,
)
from app.db.base import Base  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.document_value import DocumentValue  # noqa: E402
from app.models.document_version import DocumentVersion  # noqa: E402
from app.models.generated_file import GeneratedFile  # noqa: E402
from app.models.template import Template  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas import DocumentVersionDetail, DocumentVersionRead  # noqa: E402
from app.schemas.document import DocumentValueCreate, DocumentValueRead  # noqa: E402
from app.services.rich_text import validate_rich_content  # noqa: E402
from app.services.storage_service import storage_service  # noqa: E402

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

RICH = validate_rich_content(
    {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hi", "marks": [{"type": "bold"}]}]},
            {
                "type": "bulletList",
                "content": [{"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "one"}]}]}],
            },
        ],
    }
)
RICH_PLAIN = "Hi\n• one"


@pytest.fixture(scope="module", autouse=True)
def setup_db(tmp_path_factory):
    old_root = storage_service.root_path
    storage_service.root_path = tmp_path_factory.mktemp("versions-storage").resolve()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    storage_service.root_path = old_root


_counter = {"n": 0}


@pytest.fixture
def db():
    with TestSession() as session:
        yield session


@pytest.fixture
def document(db) -> Document:
    _counter["n"] += 1
    n = _counter["n"]
    owner = User(email=f"versions{n}@example.com", full_name=f"Owner {n}", role="faculty")
    db.add(owner)
    db.flush()
    template = Template(
        name=f"Versions {n}", category="notice", visibility="public", status="active", uploaded_by=owner.id
    )
    db.add(template)
    db.flush()
    doc = Document(template_id=template.id, created_by=owner.id, name=f"Draft {n}")
    db.add(doc)
    db.commit()
    return doc


def _save(db, document, *items):
    return upsert_values(db, document.id, list(items))


def _version_with_file(db, document, docx="d.docx", pdf=None) -> DocumentVersion:
    version = versions_crud.create_version(db, document, created_by=document.created_by, template_version=1)
    create_generated_file(db, version, docx_path=docx, generated_at=datetime(2026, 10, 18))
    if pdf:
        version.generated_file.pdf_path = pdf
    db.commit()
    return version


# ── Model + value CRUD ────────────────────────────────────────────


def test_value_validators_and_defaults(db, document):
    row = DocumentValue(document_id=document.id, field_name="x", value="v")
    assert (row.value_format, row.ai_modified) == ("plain", False)
    with pytest.raises(ValueError):
        row.value_format = "html"
    with pytest.raises(ValueError):
        row.ai_action = "rewrite"
    row.ai_action = None
    row.ai_action = "formal"


def test_upsert_rich_and_ai_flags(db, document):
    (row,) = _save(
        db,
        document,
        {"field_name": "notes", "value": RICH_PLAIN, "value_format": "rich", "rich_content": RICH,
         "ai_modified": True, "ai_action": "formal"},
    )
    assert row.value_format == "rich"
    assert json.loads(row.rich_content) == RICH
    assert (row.ai_modified, row.ai_action) == (True, "formal")
    first_time = row.ai_modified_at
    assert first_time is not None

    # Same AI state saved again: the timestamp stays.
    (row,) = _save(db, document, {"field_name": "notes", "value": RICH_PLAIN, "value_format": "rich",
                                  "rich_content": json.dumps(RICH), "ai_modified": True, "ai_action": "formal"})
    assert row.ai_modified_at == first_time

    # Another action: new timestamp.
    (row,) = _save(db, document, {"field_name": "notes", "value": RICH_PLAIN, "value_format": "rich",
                                  "rich_content": RICH, "ai_modified": True, "ai_action": "concise"})
    assert row.ai_action == "concise"
    assert row.ai_modified_at >= first_time

    # Manual edit: flags cleared; plain value clears rich_content; a stray
    # ai_action without ai_modified is not stored.
    (row,) = _save(db, document, {"field_name": "notes", "value": "typed", "rich_content": RICH,
                                  "ai_action": "tone"})
    assert (row.value_format, row.rich_content) == ("plain", None)
    assert (row.ai_modified, row.ai_action, row.ai_modified_at) == (False, None, None)

    # Plain-only clients ({field_name, value}) keep working.
    (plain,) = _save(db, document, {"field_name": "title", "value": "Hello"})
    assert (plain.value, plain.value_format, plain.ai_modified) == ("Hello", "plain", False)

    read = DocumentValueRead.model_validate(row)
    assert read.rich_content is None and read.value_format == "plain"


def test_value_schemas():
    item = DocumentValueCreate(field_name="a", value="")
    assert (item.value_format, item.rich_content, item.ai_modified, item.ai_action) == ("plain", None, False, None)
    with pytest.raises(ValueError):
        DocumentValueCreate(field_name="a", value="", value_format="html")
    with pytest.raises(ValueError):
        DocumentValueCreate(field_name="a", value="", ai_action="rewrite")
    read = DocumentValueRead(
        id=1, document_id=1, field_name="a", value="Hi", created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1), value_format="rich", rich_content=json.dumps(RICH),
    )
    assert read.rich_content == RICH
    assert DocumentValueRead(
        id=1, document_id=1, field_name="a", value="Hi", created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1), rich_content="{broken",
    ).rich_content is None


# ── Snapshots and versions ────────────────────────────────────────


def test_snapshot_shape_sorted(db, document):
    _save(
        db,
        document,
        {"field_name": "zeta", "value": "z"},
        {"field_name": "alpha", "value": RICH_PLAIN, "value_format": "rich", "rich_content": RICH,
         "ai_modified": True, "ai_action": "grammar"},
    )
    db.refresh(document)
    snapshot = versions_crud.snapshot_values(document)
    assert snapshot == [
        {"field_name": "alpha", "value": RICH_PLAIN, "value_format": "rich", "rich_content": RICH,
         "ai_modified": True, "ai_action": "grammar"},
        {"field_name": "zeta", "value": "z", "value_format": "plain", "rich_content": None,
         "ai_modified": False, "ai_action": None},
    ]
    assert versions_crud.parse_snapshot(versions_crud.dump_snapshot(snapshot)) == snapshot


def test_parse_snapshot_tolerates_bad_data():
    assert versions_crud.parse_snapshot(None) == []
    assert versions_crud.parse_snapshot("not json") == []
    assert versions_crud.parse_snapshot('{"a": 1}') == []
    parsed = versions_crud.parse_snapshot(
        json.dumps([
            {"field_name": "b", "value": 5, "value_format": "weird", "ai_action": "formal"},
            {"no": "name"},
            {"field_name": "a", "value": "x", "value_format": "rich", "rich_content": json.dumps(RICH), "ai_modified": 1, "ai_action": "tone"},
        ])
    )
    assert parsed == [
        {"field_name": "a", "value": "x", "value_format": "rich", "rich_content": RICH, "ai_modified": True, "ai_action": "tone"},
        {"field_name": "b", "value": "", "value_format": "plain", "rich_content": None, "ai_modified": False, "ai_action": None},
    ]


def test_create_list_get_versions(db, document):
    _save(db, document, {"field_name": "title", "value": "v1"})
    db.refresh(document)
    v1 = _version_with_file(db, document, "a1.docx")
    _save(db, document, {"field_name": "title", "value": "v2"})
    db.refresh(document)
    v2 = _version_with_file(db, document, "a2.docx", "a2.pdf")
    assert (v1.version, v2.version) == (1, 2)
    assert json.loads(v1.values_snapshot)[0]["value"] == "v1"
    assert json.loads(v2.values_snapshot)[0]["value"] == "v2"

    listed = versions_crud.list_versions(db, document.id)
    assert [v.version for v in listed] == [2, 1]
    assert listed[0].generated_file.docx_path == "a2.docx"
    assert listed[0].creator.full_name.startswith("Owner")
    assert versions_crud.get_version(db, document.id, 1).id == v1.id
    assert versions_crud.get_version(db, document.id, 9) is None
    assert versions_crud.count_versions(db, document.id) == 2

    db.expire_all()
    fresh = db.get(Document, document.id)
    assert [v.version for v in fresh.versions] == [2, 1]
    assert fresh.generated_file.docx_path == "a2.docx"
    assert latest_generated_file(db, document.id).docx_path == "a2.docx"


def test_create_version_retries_once_on_duplicate_number(db, document, monkeypatch):
    first = versions_crud.create_version(db, document, created_by=None, template_version=None)
    db.commit()
    real = versions_crud._next_version_number
    calls = []

    def stale_then_real(session, document_id):
        calls.append(1)
        return 1 if len(calls) == 1 else real(session, document_id)

    monkeypatch.setattr(versions_crud, "_next_version_number", stale_then_real)
    second = versions_crud.create_version(db, document, created_by=None, template_version=None, snapshot=[])
    db.commit()
    assert (first.version, second.version, len(calls)) == (1, 2, 2)

    monkeypatch.setattr(versions_crud, "_next_version_number", lambda session, document_id: 1)
    with pytest.raises(Exception):
        versions_crud.create_version(db, document, created_by=None, template_version=None, snapshot=[])
    db.rollback()


def test_latest_rows_for_many_documents(db, document):
    _version_with_file(db, document, "m1.docx")
    _version_with_file(db, document, "m2.docx")
    other = Document(template_id=document.template_id, created_by=document.created_by, name="Other")
    db.add(other)
    db.commit()
    _version_with_file(db, other, "o1.docx")
    rows = get_generated_files_for_documents(db, [document.id, other.id, 999999])
    assert {doc_id: row.docx_path for doc_id, row in rows.items()} == {
        document.id: "m2.docx",
        other.id: "o1.docx",
    }
    assert get_generated_files_for_documents(db, []) == {}


def test_diff_snapshots():
    def item(name, value="", fmt="plain", rich=None):
        return {"field_name": name, "value": value, "value_format": fmt, "rich_content": rich,
                "ai_modified": False, "ai_action": None}

    prev = [item("a", "1"), item("b", "x"), item("c", "same"), item("gone")]
    curr = [item("a", "2"), item("b", "x", "rich", RICH), item("c", "same"), item("new")]
    assert versions_crud.diff_snapshots(prev, curr) == ["a", "b", "gone", "new"]
    assert versions_crud.diff_snapshots(None, curr) == []
    # The AI flag alone is not a content change.
    flagged = [dict(item("c", "same"), ai_modified=True, ai_action="formal")]
    assert versions_crud.diff_snapshots([item("c", "same")], flagged) == []


def test_changed_fields_by_version(db, document):
    _save(db, document, {"field_name": "title", "value": "one"}, {"field_name": "venue", "value": "Hall"})
    db.refresh(document)
    _version_with_file(db, document, "c1.docx")
    _save(db, document, {"field_name": "title", "value": "two"})
    db.refresh(document)
    _version_with_file(db, document, "c2.docx")
    _version_with_file(db, document, "c3.docx")
    changed = versions_crud.changed_fields_by_version(versions_crud.list_versions(db, document.id))
    assert changed == {1: [], 2: ["title"], 3: []}


def test_restore_values(db, document):
    _save(
        db,
        document,
        {"field_name": "title", "value": "Original"},
        {"field_name": "notes", "value": RICH_PLAIN, "value_format": "rich", "rich_content": RICH,
         "ai_modified": True, "ai_action": "formal"},
    )
    db.refresh(document)
    v1 = _version_with_file(db, document, "r1.docx")
    before = db.get(Document, document.id).updated_at

    _save(db, document, {"field_name": "title", "value": "Changed"}, {"field_name": "notes", "value": "plain now"},
          {"field_name": "extra", "value": "added later"})
    restored = versions_crud.restore_values(db, document, v1)
    db.commit()
    assert {row.field_name for row in restored} == {"title", "notes"}

    rows = {row.field_name: row for row in db.execute(
        select(DocumentValue).where(DocumentValue.document_id == document.id)).scalars()}
    assert set(rows) == {"title", "notes"}  # "extra" deleted
    assert rows["title"].value == "Original"
    notes = rows["notes"]
    assert (notes.value_format, json.loads(notes.rich_content), notes.value) == ("rich", RICH, RICH_PLAIN)
    assert (notes.ai_modified, notes.ai_action) == (True, "formal")
    assert notes.ai_modified_at is not None
    db.refresh(document)
    assert document.updated_at >= before
    assert versions_crud.snapshot_values(document) == versions_crud.parse_snapshot(v1)


def test_prune_old_version_files(db, document):
    for n in (1, 2, 3):
        _version_with_file(db, document, f"p{n}.docx", f"p{n}.pdf" if n != 2 else None)
    assert versions_crud.prune_old_version_files(db, document.id, keep=2) == ["p1.docx", "p1.pdf"]
    db.commit()
    rows = {v.version: v.generated_file for v in versions_crud.list_versions(db, document.id)}
    assert rows[1].files_pruned_at is not None and rows[1].files_pruned is True
    assert rows[1].has_pdf is False  # pruned: no longer downloadable
    assert rows[1].docx_path == "p1.docx"  # paths kept for reference
    assert rows[2].files_pruned_at is None and rows[3].files_pruned_at is None
    # Idempotent; a smaller keep prunes the next one (no PDF there).
    assert versions_crud.prune_old_version_files(db, document.id, keep=2) == []
    assert versions_crud.prune_old_version_files(db, document.id, keep=1) == ["p2.docx"]
    assert versions_crud.prune_old_version_files(db, document.id, keep=0) == []  # at least 1 kept
    db.commit()
    assert versions_crud.count_versions(db, document.id) == 3  # rows kept


def test_keep_files_setting():
    assert settings.generated_versions_keep_files >= 1
    base = {"DATABASE_URL": "sqlite://", "JWT_SECRET_KEY": "x" * 40}
    assert Settings(**base).generated_versions_keep_files == 10
    assert Settings(**base, GENERATED_VERSIONS_KEEP_FILES=2).generated_versions_keep_files == 2
    with pytest.raises(ValueError):
        Settings(**base, GENERATED_VERSIONS_KEEP_FILES=0)


# ── Cascades ──────────────────────────────────────────────────────


def test_document_delete_cascades_versions_rows_and_files(db, document):
    paths = []
    for n in (1, 2):
        docx = storage_service.save_bytes("generated_docx", f"cascade{n}.docx", b"PK").path
        pdf = storage_service.save_bytes("generated_pdf", f"cascade{n}.pdf", b"%PDF").path
        paths += [docx, pdf]
        _version_with_file(db, document, docx, pdf)
    document_id = document.id
    assert delete_document(db, document_id) is True
    assert db.execute(select(DocumentVersion).where(DocumentVersion.document_id == document_id)).first() is None
    assert db.execute(select(GeneratedFile).where(GeneratedFile.document_id == document_id)).first() is None
    assert not any(storage_service.exists(path) for path in paths)


def test_creator_delete_sets_version_created_by_null(db, document):
    editor = User(email=f"editor{document.id}@example.com", full_name="Editor", role="faculty")
    db.add(editor)
    db.commit()
    version = versions_crud.create_version(db, document, created_by=editor.id, template_version=None)
    db.commit()
    db.delete(editor)
    db.commit()
    db.expire_all()
    assert db.get(DocumentVersion, version.id).created_by is None


# ── Schemas ───────────────────────────────────────────────────────


def test_version_schemas():
    read = DocumentVersionRead(
        version=2, created_at=datetime(2026, 10, 18), created_by_name="Priya", template_version=1,
        pdf_status="converted", has_docx=True, has_pdf=True, files_pruned=False,
        changed_fields=["title"], is_latest=True,
    )
    assert read.docx_url is None and read.pdf_error is None
    detail = DocumentVersionDetail(**read.model_dump(), document_id=7, sections=[])
    assert detail.document_id == 7
