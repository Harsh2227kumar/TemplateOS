#!/usr/bin/env python3
"""
V1.7 Phase 1 - Preview demo seeder.

Creates (idempotently) a "Preview Demo" template with one field of every type
spread over 3 sections plus one field without a section, and a draft
"Preview Demo Draft" whose values cover every preview state: filled,
blank text, list with blank items, list with a blank item dropped, a
required field never saved, and an optional field with a default_value that
was never saved (the preview shows it empty, like generation does).

Safety: refuses to run unless the database URL is SQLite, or --yes is passed.
This keeps a stray DATABASE_URL (the shared Neon database) from being seeded
by accident.

Run from backend/ (needs at least one user; create one with seed_user.py):
    python scripts/seed_preview_demo.py
    python scripts/seed_preview_demo.py --database-url sqlite:///./dev.db
    python scripts/seed_preview_demo.py --yes        # non-SQLite, on purpose
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEMPLATE_NAME = "Preview Demo"
DOCUMENT_NAME = "Preview Demo Draft"

# (field_name, field_label, field_type, section, is_required, ai_enabled, default_value)
DEMO_FIELDS = [
    ("meeting_title", "Meeting Title", "text", "Meeting Details", True, False, None),
    ("meeting_date", "Meeting Date", "date", "Meeting Details", True, False, None),
    ("venue", "Venue", "text", "Meeting Details", False, True, None),
    ("agenda_items", "Agenda Items", "list", "Discussion", True, True, None),
    ("summary", "Discussion Summary", "textarea", "Discussion", True, True, None),
    ("attendees_count", "Attendees", "number", "Discussion", False, False, None),
    ("verified_by", "Verified By", "text", "Approval", True, False, None),
    ("approved_by", "Approved By", "signature", "Approval", True, False, None),
    ("action_items", "Action Items", "list", "Approval", False, False, None),
    ("reference_no", None, "text", None, False, False, "REF-2026-001"),
]

# Saved values; fields not listed here are never saved.
DEMO_VALUES = {
    "meeting_title": "Academic Committee Meeting",
    "meeting_date": "2026-10-14",
    "agenda_items": '["Budget review", "", "Lab schedule"]',
    "summary": "Budget approved.\nLab hours extended to 8 pm.",
    "attendees_count": "24",
    "verified_by": "   ",
    "action_items": '["", " "]',
}


def is_sqlite_url(url: str) -> bool:
    return url.strip().lower().startswith("sqlite")


def check_target(url: str, assume_yes: bool) -> str | None:
    """None when seeding may proceed, else the refusal message."""
    if is_sqlite_url(url) or assume_yes:
        return None
    return (
        "Refusing to seed: the database URL is not SQLite. This may be a shared "
        "database. Re-run with --yes if you really mean it."
    )


def seed(db) -> tuple[object, object]:
    """Create or complete the demo template and draft. Returns (template, document)."""
    from sqlalchemy import select

    from app.models.document import Document
    from app.models.document_value import DocumentValue
    from app.models.template import Template
    from app.models.template_field import TemplateField
    from app.models.user import User

    owner = db.scalars(select(User).where(User.role == "super_admin")).first()
    owner = owner or db.scalars(select(User).order_by(User.id)).first()
    if owner is None:
        raise RuntimeError("No users found. Create one first (scripts/seed_user.py).")

    template = db.scalars(
        select(Template).where(
            Template.name == TEMPLATE_NAME, Template.uploaded_by == owner.id
        )
    ).first()
    if template is None:
        template = Template(
            name=TEMPLATE_NAME,
            description="Every field type and preview state (V1.7 Phase 1 demo)",
            category="mom",
            visibility="private",
            status="active",
            uploaded_by=owner.id,
        )
        db.add(template)
        db.flush()

    existing = {
        field.field_name
        for field in db.scalars(
            select(TemplateField).where(TemplateField.template_id == template.id)
        )
    }
    for order, (name, label, ftype, section, required, ai, default) in enumerate(
        DEMO_FIELDS
    ):
        if name in existing:
            continue
        db.add(
            TemplateField(
                template_id=template.id,
                field_name=name,
                field_label=label,
                field_type=ftype,
                section=section,
                is_required=required,
                ai_enabled=ai,
                default_value=default,
                display_order=order,
                source="manual",
            )
        )

    document = db.scalars(
        select(Document).where(
            Document.template_id == template.id,
            Document.created_by == owner.id,
            Document.name == DOCUMENT_NAME,
        )
    ).first()
    if document is None:
        document = Document(
            template_id=template.id, created_by=owner.id, name=DOCUMENT_NAME
        )
        db.add(document)
        db.flush()

    saved = {
        value.field_name: value
        for value in db.scalars(
            select(DocumentValue).where(DocumentValue.document_id == document.id)
        )
    }
    for name, raw in DEMO_VALUES.items():
        if name in saved:
            saved[name].value = raw
        else:
            db.add(DocumentValue(document_id=document.id, field_name=name, value=raw))

    db.commit()
    return template, document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--database-url",
        help="Database to seed (default: DATABASE_URL from settings).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Allow a non-SQLite database URL.",
    )
    args = parser.parse_args(argv)

    url = args.database_url
    if url is None:
        from app.core.config import settings

        url = settings.database_url

    refusal = check_target(url, args.yes)
    if refusal:
        print(f"[ERROR] {refusal}")
        return 2

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    import app.models  # noqa: F401  (register every mapper)

    engine = create_engine(url)
    try:
        with Session(engine) as db:
            template, document = seed(db)
            print(f"[OK] Template '{TEMPLATE_NAME}' id={template.id}")
            print(f"[OK] Draft '{DOCUMENT_NAME}' id={document.id}")
            print(f"[INFO] Preview: GET /api/v1/documents/{document.id}/preview")
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
