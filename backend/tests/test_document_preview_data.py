"""
V1.7 Phase 1 - Preview data layer (Member 3).

Coverage:
- get_document_for_preview: loads document, values, template, fields and
  generated_file in <= 4 SQL statements (counted with before_cursor_execute),
  nothing lazy-loads afterwards, None for a missing id.
- build_sections: (display_order, id) ordering, null/blank section ->
  "General", section order by first field, labels, never-saved fields
  (value None, default_value NOT used: generation ignores it), list items
  with blanks dropped, invalid list JSON as one item, formatter injection.
- compute_completeness: blank text, blank list items, optional fields.
- field_is_empty parity with app/services/document_validator.py.
- DocumentPreview round-trips a realistic payload.
- scripts/seed_preview_demo.py: SQLite guard and idempotent seeding.

Database: in-memory SQLite with PRAGMA foreign_keys=ON.
"""

import importlib.util
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault(
    "JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests"
)

import app.models  # noqa: F401,E402  (register every mapper)
from app.crud.document_crud import get_document_for_preview  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.document_value import DocumentValue  # noqa: E402
from app.models.document_version import DocumentVersion  # noqa: E402
from app.models.generated_file import GeneratedFile  # noqa: E402
from app.models.organization import Department, Organization  # noqa: E402
from app.models.template import Template  # noqa: E402
from app.models.template_field import TemplateField  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas import DocumentPreview  # noqa: E402
from app.schemas.document_preview import (  # noqa: E402
    PreviewDocument,
    PreviewGeneration,
    PreviewPermissions,
    PreviewTemplate,
)
from app.services.document_preview import (  # noqa: E402
    GENERAL_SECTION,
    build_sections,
    compute_completeness,
    field_is_empty,
    field_label,
    list_items,
    saved_values,
)
from app.services.document_validator import validate_document_values  # noqa: E402
from app.services.generation_service import build_context  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]

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


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def generation_format(field, raw: str) -> str:
    """The formatter Member 2 injects: generation_service's own rule."""
    return str(build_context([field], {field.field_name: raw})[field.field_name])


def _field(name, field_type="text", **kwargs) -> TemplateField:
    return TemplateField(field_name=name, field_type=field_type, **kwargs)


class StatementCounter:
    def __init__(self, bind):
        self.bind = bind
        self.statements: list[str] = []

    def _on_execute(self, _conn, _cursor, statement, *_args):
        self.statements.append(statement)

    def __enter__(self):
        event.listen(self.bind, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *_exc):
        event.remove(self.bind, "before_cursor_execute", self._on_execute)

    @property
    def count(self) -> int:
        return len(self.statements)


_counter = iter(range(1, 10_000))


def _make_document(db: Session, *, with_generated: bool, with_scope: bool) -> int:
    n = next(_counter)
    owner = User(email=f"preview{n}@example.com", full_name="Preview Owner")
    db.add(owner)
    db.flush()
    template = Template(
        name=f"Preview Template {n}",
        category="mom",
        visibility="private",
        status="active",
        uploaded_by=owner.id,
        processed_file_path="templates/processed/x.docx",
    )
    if with_scope:
        org = Organization(name=f"Org {n}")
        db.add(org)
        db.flush()
        dept = Department(organization_id=org.id, name=f"Dept {n}")
        db.add(dept)
        db.flush()
        template.scope_organization_id = org.id
        template.scope_department_id = dept.id
    db.add(template)
    db.flush()
    for order, (name, ftype) in enumerate(
        [("title", "text"), ("meeting_date", "date"), ("agenda", "list")]
    ):
        db.add(
            TemplateField(
                template_id=template.id,
                field_name=name,
                field_type=ftype,
                display_order=order,
            )
        )
    document = Document(template_id=template.id, created_by=owner.id, name="Draft")
    db.add(document)
    db.flush()
    db.add_all(
        [
            DocumentValue(document_id=document.id, field_name="title", value="Hello"),
            DocumentValue(
                document_id=document.id, field_name="agenda", value='["a", " ", "b"]'
            ),
        ]
    )
    if with_generated:
        version = DocumentVersion(document_id=document.id, version=1, values_snapshot="[]")
        db.add(version)
        db.flush()
        db.add(
            GeneratedFile(
                document_id=document.id,
                version_id=version.id,
                docx_path="generated/docx/draft-1.docx",
                pdf_path="generated/pdf/draft-1.pdf",
                pdf_status="converted",
                template_version=1,
            )
        )
    db.commit()
    return document.id


# --- get_document_for_preview ---


@pytest.mark.parametrize(
    "with_generated, with_scope",
    [(True, True), (False, False), (True, False)],
)
def test_preview_query_loads_everything_in_few_statements(with_generated, with_scope):
    with TestSession() as db:
        document_id = _make_document(
            db, with_generated=with_generated, with_scope=with_scope
        )

    with TestSession() as db:
        with StatementCounter(engine) as counter:
            document = get_document_for_preview(db, document_id)
            assert document is not None
            loaded = counter.count

            # Everything the preview reads is already loaded: no lazy loads.
            assert document.template.name.startswith("Preview Template")
            assert sorted(f.field_name for f in document.template.fields) == [
                "agenda",
                "meeting_date",
                "title",
            ]
            assert saved_values(document.values) == {
                "title": "Hello",
                "agenda": '["a", " ", "b"]',
            }
            if with_generated:
                assert document.generated_file.pdf_status == "converted"
            else:
                assert document.generated_file is None
            assert counter.count == loaded

    assert loaded <= 4, counter.statements
    assert loaded == 3, counter.statements


def test_preview_query_missing_document_returns_none():
    with TestSession() as db:
        with StatementCounter(engine) as counter:
            assert get_document_for_preview(db, 987654) is None
        assert counter.count == 1


# --- labels / list items / emptiness ---


def test_field_label_falls_back_to_field_name():
    assert field_label(_field("meeting_date", field_label="Meeting Date")) == "Meeting Date"
    assert field_label(_field("meeting_date", field_label="  Date  ")) == "Date"
    assert field_label(_field("meeting_date", field_label=None)) == "meeting_date"
    assert field_label(_field("meeting_date", field_label="   ")) == "meeting_date"


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, []),
        ("", []),
        ("   ", []),
        ("[]", []),
        ('["", " "]', []),
        ('["a", "", " b "]', ["a", " b "]),
        ("not json", ["not json"]),
        ('"single"', ["single"]),
    ],
)
def test_list_items(raw, expected):
    assert list_items(raw) == expected


def _validator_says_empty(field_type: str, raw: str) -> bool:
    """Ask the real save validator whether a REQUIRED field with raw is empty."""
    field = _field("probe", field_type, is_required=True)
    try:
        validate_document_values([field], [{"field_name": "probe", "value": raw}])
    except HTTPException as exc:
        errors = [error["error"] for error in exc.detail]
        assert errors != ["Must be a valid list (JSON array of strings)"], (
            "parity cases must be inputs the validator accepts"
        )
        return errors == ["This field is required"]
    return False


PARITY_CASES = [
    ("text", ""),
    ("text", " "),
    ("text", "\n\t "),
    ("text", "a"),
    ("text", "  a  "),
    ("textarea", "  \n  "),
    ("textarea", "line one\nline two"),
    ("date", ""),
    ("date", "2026-10-14"),
    ("number", ""),
    ("number", "   "),
    ("number", "12.5"),
    ("signature", ""),
    ("signature", "signatures/u1.png"),
    ("list", ""),
    ("list", "  "),
    ("list", "[]"),
    ("list", '[""]'),
    ("list", '["", " "]'),
    ("list", '[" \\n\\t"]'),
    ("list", '["a"]'),
    ("list", '["", "b"]'),
    ("list", '[" a "]'),
]


@pytest.mark.parametrize("field_type, raw", PARITY_CASES)
def test_field_is_empty_matches_save_validator(field_type, raw):
    assert field_is_empty(field_type, raw) is _validator_says_empty(field_type, raw)


def test_field_is_empty_never_saved_matches_generation_check():
    # Generation validates a missing value as "" (document_generation._validate_required).
    for field_type in ("text", "date", "number", "list", "signature", "textarea"):
        assert field_is_empty(field_type, None) is True
        assert _validator_says_empty(field_type, "") is True


@pytest.mark.parametrize("raw", ['"abc"', "not json", "[1, 2]", '{"a": "b"}'])
def test_field_is_empty_invalid_list_is_one_item(raw):
    # The validator rejects these at save time; if one is stored anyway it is
    # shown as one item (like generation), so it is not empty.
    field = _field("probe", "list", is_required=True)
    with pytest.raises(HTTPException):
        validate_document_values([field], [{"field_name": "probe", "value": raw}])
    assert field_is_empty("list", raw) is False


# --- build_sections ---


def _sample_fields() -> list[TemplateField]:
    return [
        _field("approved_by", "signature", id=9, section="Approval", display_order=5),
        _field("notes", "textarea", id=7, section=None, display_order=4, is_required=False),
        _field("meeting_date", "date", id=2, section="Meeting", display_order=1,
               field_label="Meeting Date"),
        _field("agenda", "list", id=3, section="  ", display_order=2),
        _field("venue", "text", id=4, section="Meeting", display_order=3,
               is_required=False, default_value="Main Hall", ai_enabled=True),
        _field("title", "text", id=5, section="Meeting", display_order=0),
        _field("bad_list", "list", id=6, section="Approval", display_order=5,
               is_required=False),
    ]


SAMPLE_VALUES = {
    "title": "Academic Committee",
    "meeting_date": "2026-10-14",
    "agenda": '["Budget", "", " ", "Labs"]',
    "notes": "   ",
    "bad_list": "not json",
}


def test_build_sections_order_and_general_section():
    sections = build_sections(_sample_fields(), SAMPLE_VALUES, generation_format)

    # Section order follows each section's first field (display_order, id).
    assert [s.name for s in sections] == ["Meeting", GENERAL_SECTION, "Approval"]
    assert [f.field_name for f in sections[0].fields] == [
        "title",
        "meeting_date",
        "venue",
    ]
    # Blank ("  ") and None sections are both "General".
    assert [f.field_name for f in sections[1].fields] == ["agenda", "notes"]
    # Same display_order (5) -> lower id (6 < 9) first.
    assert [f.field_name for f in sections[2].fields] == ["bad_list", "approved_by"]


def test_build_sections_values_and_formatting():
    sections = build_sections(_sample_fields(), SAMPLE_VALUES, generation_format)
    fields = {f.field_name: f for s in sections for f in s.fields}

    date = fields["meeting_date"]
    assert date.label == "Meeting Date"
    assert date.value == "2026-10-14"
    assert date.display_value == "14-10-2026"
    assert date.items is None
    assert (date.is_empty, date.missing_required) == (False, False)

    agenda = fields["agenda"]
    assert agenda.label == "agenda"
    assert agenda.items == ["Budget", "Labs"]
    assert agenda.display_value == "Budget\nLabs"
    assert agenda.is_empty is False

    notes = fields["notes"]
    assert notes.value == "   "
    assert notes.display_value == ""
    assert (notes.is_empty, notes.missing_required) == (True, False)

    bad = fields["bad_list"]
    assert bad.items == ["not json"]
    assert bad.display_value == "not json"
    assert bad.is_empty is False


def test_build_sections_never_saved_fields_ignore_default_value():
    sections = build_sections(_sample_fields(), SAMPLE_VALUES, generation_format)
    fields = {f.field_name: f for s in sections for f in s.fields}

    # Generation renders only saved values, so a default_value never saved
    # is not in the document yet: the preview shows the field empty.
    venue = fields["venue"]
    assert venue.value is None
    assert venue.display_value == ""
    assert (venue.is_empty, venue.missing_required, venue.ai_enabled) == (
        True,
        False,
        True,
    )
    approved = fields["approved_by"]
    assert approved.value is None
    assert (approved.is_empty, approved.missing_required) == (True, True)


def test_build_sections_formatter_is_injected_and_skipped_for_empty():
    calls = []

    def formatter(field, raw):
        calls.append(field.field_name)
        return f"<{raw}>"

    sections = build_sections(_sample_fields(), SAMPLE_VALUES, formatter)
    fields = {f.field_name: f for s in sections for f in s.fields}
    assert fields["title"].display_value == "<Academic Committee>"
    assert fields["notes"].display_value == ""
    assert sorted(calls) == ["agenda", "bad_list", "meeting_date", "title"]


def test_build_sections_empty_template():
    assert build_sections([], {}, generation_format) == []


# --- compute_completeness ---


def test_compute_completeness():
    fields = [
        _field("blank_text", "text", id=1, display_order=3),
        _field("blank_list", "list", id=2, display_order=1),
        _field("filled_list", "list", id=3, display_order=2),
        _field("filled_text", "text", id=4, display_order=0),
        _field("never_saved", "date", id=5, display_order=4, default_value="2026-01-01"),
        _field("optional_blank", "text", id=6, display_order=5, is_required=False),
        _field("optional_list", "list", id=7, display_order=6, is_required=False),
    ]
    values = {
        "blank_text": "  ",
        "blank_list": '["", " "]',
        "filled_list": '["a"]',
        "filled_text": "x",
        "optional_blank": "",
        "optional_list": "[]",
    }
    result = compute_completeness(fields, values)
    assert result.required_total == 5
    assert result.required_filled == 2
    # Display order, not field-list order.
    assert result.missing_required == ["blank_list", "blank_text", "never_saved"]


def test_compute_completeness_no_required_fields():
    result = compute_completeness([_field("x", is_required=False)], {})
    assert (result.required_total, result.required_filled, result.missing_required) == (
        0,
        0,
        [],
    )


# --- schemas ---


def test_document_preview_round_trip_from_query():
    with TestSession() as db:
        document_id = _make_document(db, with_generated=True, with_scope=False)

    with TestSession() as db:
        document = get_document_for_preview(db, document_id)
        template = document.template
        values = saved_values(document.values)
        record = document.generated_file
        preview = DocumentPreview(
            document=PreviewDocument.model_validate(document),
            template=PreviewTemplate(
                id=template.id,
                name=template.name,
                category=template.category,
                version=template.version,
                has_processed_file=bool(template.processed_file_path),
            ),
            completeness=compute_completeness(template.fields, values),
            sections=build_sections(template.fields, values, generation_format),
            generation=PreviewGeneration(
                generated_at=record.generated_at,
                is_stale=document.updated_at > record.generated_at,
                template_version=record.template_version,
                docx_available=True,
                docx_url=f"/api/v1/documents/{document.id}/download?format=docx",
                pdf_status=record.pdf_status,
                pdf_error=record.pdf_error,
                pdf_available=True,
                pdf_url=f"/api/v1/documents/{document.id}/download/pdf",
                pdf_filename=Path(record.pdf_path).name,
            ),
            permissions=PreviewPermissions(
                can_edit=True, can_generate=True, can_download=True
            ),
        )

    dumped = preview.model_dump(mode="json")
    assert DocumentPreview.model_validate(dumped) == preview
    assert DocumentPreview.model_validate_json(preview.model_dump_json()) == preview

    assert dumped["completeness"] == {
        "required_total": 3,
        "required_filled": 2,
        "missing_required": ["meeting_date"],
    }
    assert [s["name"] for s in dumped["sections"]] == [GENERAL_SECTION]
    agenda = dumped["sections"][0]["fields"][2]
    assert agenda["items"] == ["a", "b"]
    assert dumped["generation"]["pdf_filename"] == "draft-1.pdf"
    # No storage paths leak into the payload.
    assert "generated/" not in json.dumps(dumped)


def test_document_preview_generation_optional_and_status_checked():
    now = datetime(2026, 10, 15, 9, 0)
    payload = {
        "document": {"id": 1, "name": None, "status": "draft",
                     "created_at": now, "updated_at": now + timedelta(minutes=5)},
        "template": {"id": 2, "name": "T", "category": "mom", "version": 1,
                     "has_processed_file": False},
        "completeness": {"required_total": 0, "required_filled": 0,
                         "missing_required": []},
        "sections": [],
        "generation": None,
        "permissions": {"can_edit": False, "can_generate": False,
                        "can_download": False},
    }
    assert DocumentPreview.model_validate(payload).generation is None

    with pytest.raises(ValueError):
        PreviewGeneration(
            generated_at=now, is_stale=False, template_version=None,
            docx_available=False, docx_url="/x", pdf_status="done",
            pdf_error=None, pdf_available=False, pdf_url=None, pdf_filename=None,
        )


# --- scripts/seed_preview_demo.py ---


def _load_seed_script():
    path = BACKEND_DIR / "scripts" / "seed_preview_demo.py"
    spec = importlib.util.spec_from_file_location("seed_preview_demo", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_script = _load_seed_script()


@pytest.mark.parametrize(
    "url, yes, allowed",
    [
        ("sqlite://", False, True),
        ("sqlite:///./dev.db", False, True),
        ("SQLite:///C:/x.db", False, True),
        ("postgresql+psycopg://u:p@ep-x.neon.tech/db", False, False),
        ("postgresql://u:p@localhost/db", False, False),
        ("mysql://u:p@localhost/db", False, False),
        ("postgresql+psycopg://u:p@ep-x.neon.tech/db", True, True),
    ],
)
def test_seed_script_guard(url, yes, allowed):
    assert (seed_script.check_target(url, yes) is None) is allowed


def test_seed_script_refuses_non_sqlite_without_connecting(monkeypatch, capsys):
    import sqlalchemy

    def boom(*_args, **_kwargs):
        raise AssertionError("must not create an engine")

    monkeypatch.setattr(sqlalchemy, "create_engine", boom)
    code = seed_script.main(["--database-url", "postgresql://u:p@db.neon.tech/x"])
    assert code == 2
    assert "Refusing" in capsys.readouterr().out


def test_seed_script_seeds_idempotently(tmp_path):
    url = f"sqlite:///{(tmp_path / 'seed.db').as_posix()}"
    file_engine = create_engine(url)
    try:
        Base.metadata.create_all(bind=file_engine)
        with Session(file_engine) as db:
            db.add(User(email="seed@example.com", full_name="Seed Owner"))
            db.commit()

        assert seed_script.main(["--database-url", url]) == 0
        assert seed_script.main(["--database-url", url]) == 0

        with Session(file_engine) as db:
            assert db.scalar(select(func.count()).select_from(Template)) == 1
            assert db.scalar(select(func.count()).select_from(TemplateField)) == len(
                seed_script.DEMO_FIELDS
            )
            assert db.scalar(select(func.count()).select_from(Document)) == 1
            assert db.scalar(select(func.count()).select_from(DocumentValue)) == len(
                seed_script.DEMO_VALUES
            )
            document = db.scalars(select(Document)).one()
            loaded = get_document_for_preview(db, document.id)
            fields = loaded.template.fields
            values = saved_values(loaded.values)
            types = {f.field_type for f in fields}
            assert types == {"text", "textarea", "date", "number", "list", "signature"}
            sections = build_sections(fields, values, generation_format)
            assert [s.name for s in sections] == [
                "Meeting Details",
                "Discussion",
                "Approval",
                GENERAL_SECTION,
            ]
            completeness = compute_completeness(fields, values)
            assert completeness.missing_required == ["verified_by", "approved_by"]
    finally:
        file_engine.dispose()


def test_seed_script_needs_a_user(tmp_path, capsys):
    url = f"sqlite:///{(tmp_path / 'empty.db').as_posix()}"
    file_engine = create_engine(url)
    try:
        Base.metadata.create_all(bind=file_engine)
    finally:
        file_engine.dispose()
    assert seed_script.main(["--database-url", url]) == 1
    assert "No users" in capsys.readouterr().out
