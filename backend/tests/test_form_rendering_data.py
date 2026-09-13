# backend/tests/test_form_rendering_data.py
"""
V1.4 Phase 1 - Form Rendering Data Contract Tests

Simplified tests that verify template_fields data structure
is ready for dynamic form rendering (Phase 1 verification only).
"""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-v14-phase1")

from app.db.base import Base
from app.models.user import User
from app.models.template import Template
from app.models.template_field import TemplateField, FIELD_TYPES

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db():
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)

def test_field_types_are_mvp_set():
    """Test that FIELD_TYPES matches the MVP set."""
    mvp_types = {"text", "textarea", "date", "number", "list", "signature"}
    assert set(FIELD_TYPES) == mvp_types

def test_template_field_model_has_all_metadata(db):
    """Test that TemplateField model has all required metadata columns."""
    # Create a user
    user = User(email="test@example.com", full_name="Test User", hashed_password="hash")
    db.add(user)
    db.flush()

    # Create a template
    template = Template(
        name="Test Template",
        category="mom",
        visibility="public",
        status="field_configured",
        uploaded_by=user.id,
        original_filename="test.docx",
        original_file_path="templates/original/test.docx"
    )
    db.add(template)
    db.flush()

    # Create a field with all metadata
    field = TemplateField(
        template_id=template.id,
        field_name="test_field",
        field_label="Test Field",
        field_type="text",
        is_required=True,
        description="Test description",
        example_value="Example",
        validation_rule="email",
        section="Test Section",
        ai_enabled=True,
        display_order=0
    )
    db.add(field)
    db.commit()

    # Verify all attributes exist
    retrieved = db.query(TemplateField).filter_by(field_name="test_field").first()
    assert retrieved is not None
    assert retrieved.field_name == "test_field"
    assert retrieved.field_label == "Test Field"
    assert retrieved.field_type == "text"
    assert retrieved.is_required is True
    assert retrieved.description == "Test description"
    assert retrieved.example_value == "Example"
    assert retrieved.validation_rule == "email"
    assert retrieved.section == "Test Section"
    assert retrieved.ai_enabled is True
    assert retrieved.display_order == 0

def test_fields_ordered_by_display_order(db):
    """Test that fields can be ordered by display_order."""
    user = User(email="test@example.com", full_name="Test", hashed_password="hash")
    db.add(user)
    db.flush()

    template = Template(
        name="Test", category="mom", visibility="public",
        status="field_configured", uploaded_by=user.id,
        original_filename="test.docx", original_file_path="test.docx"
    )
    db.add(template)
    db.flush()

    # Create fields in random order
    fields_data = [
        {"field_name": "field_2", "display_order": 2},
        {"field_name": "field_0", "display_order": 0},
        {"field_name": "field_1", "display_order": 1},
    ]

    for fd in fields_data:
        field = TemplateField(
            template_id=template.id,
            field_name=fd["field_name"],
            field_type="text",
            display_order=fd["display_order"]
        )
        db.add(field)
    db.commit()

    # Query ordered by display_order
    ordered_fields = db.query(TemplateField).filter_by(
        template_id=template.id
    ).order_by(TemplateField.display_order).all()

    assert len(ordered_fields) == 3
    assert ordered_fields[0].field_name == "field_0"
    assert ordered_fields[1].field_name == "field_1"
    assert ordered_fields[2].field_name == "field_2"

def test_fields_can_be_grouped_by_section(db):
    """Test that fields with sections can be grouped."""
    user = User(email="test@example.com", full_name="Test", hashed_password="hash")
    db.add(user)
    db.flush()

    template = Template(
        name="Test", category="mom", visibility="public",
        status="field_configured", uploaded_by=user.id,
        original_filename="test.docx", original_file_path="test.docx"
    )
    db.add(template)
    db.flush()

    # Create fields with different sections
    fields = [
        TemplateField(template_id=template.id, field_name="title", section="Details", display_order=0, field_type="text"),
        TemplateField(template_id=template.id, field_name="date", section="Details", display_order=1, field_type="date"),
        TemplateField(template_id=template.id, field_name="summary", section="Content", display_order=2, field_type="textarea"),
        TemplateField(template_id=template.id, field_name="notes", section=None, display_order=3, field_type="text"),
    ]
    for f in fields:
        db.add(f)
    db.commit()

    # Group by section
    all_fields = db.query(TemplateField).filter_by(template_id=template.id).order_by(TemplateField.display_order).all()
    sections = {}
    for field in all_fields:
        sec = field.section or "General"
        if sec not in sections:
            sections[sec] = []
        sections[sec].append(field)

    assert "Details" in sections
    assert "Content" in sections
    assert "General" in sections
    assert len(sections["Details"]) == 2
    assert len(sections["Content"]) == 1
    assert len(sections["General"]) == 1

def test_validation_rule_persists(db):
    """Test that validation_rule is stored and retrieved."""
    user = User(email="test@example.com", full_name="Test", hashed_password="hash")
    db.add(user)
    db.flush()

    template = Template(
        name="Test", category="mom", visibility="public",
        status="field_configured", uploaded_by=user.id,
        original_filename="test.docx", original_file_path="test.docx"
    )
    db.add(template)
    db.flush()

    field = TemplateField(
        template_id=template.id,
        field_name="email",
        field_type="text",
        validation_rule="email",
        display_order=0
    )
    db.add(field)
    db.commit()

    retrieved = db.query(TemplateField).filter_by(field_name="email").first()
    assert retrieved.validation_rule == "email"
