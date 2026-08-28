"""
CRUD helpers for template_fields (V1.3 Phase 1 — Member 3).

Member 2's detection endpoint persists through these:
- bulk_create_fields          -> first-run / force re-detect writes
- get_fields_by_template      -> ordered read (display_order, id)
- delete_fields_by_template   -> force re-detect clears old rows first
- field_exists                -> idempotency guard
"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.template_field import TemplateField
from app.schemas.template_field import TemplateFieldCreate


def bulk_create_fields(
    db: Session,
    template_id: int,
    fields: list[TemplateFieldCreate],
) -> list[TemplateField]:
    """Bulk-insert field rows for a template and return the refreshed rows in input order."""
    if not fields:
        return []
    db_objs = [
        TemplateField(template_id=template_id, **field.model_dump()) for field in fields
    ]
    db.add_all(db_objs)
    db.commit()
    for obj in db_objs:
        db.refresh(obj)
    return db_objs


def get_fields_by_template(db: Session, template_id: int) -> list[TemplateField]:
    """Return a template's fields ordered by display_order, then id (first-seen order)."""
    result = db.execute(
        select(TemplateField)
        .where(TemplateField.template_id == template_id)
        .order_by(TemplateField.display_order, TemplateField.id)
    )
    return list(result.scalars().all())


def delete_fields_by_template(db: Session, template_id: int) -> int:
    """Delete all field rows for a template. Returns the number of rows deleted."""
    result = db.execute(
        delete(TemplateField).where(TemplateField.template_id == template_id)
    )
    db.commit()
    return result.rowcount or 0


def field_exists(db: Session, template_id: int, field_name: str) -> bool:
    """Return True if the template already has a field with the given key."""
    result = db.execute(
        select(func.count(TemplateField.id)).where(
            TemplateField.template_id == template_id,
            TemplateField.field_name == field_name,
        )
    )
    return (result.scalar() or 0) > 0


def next_display_order(db: Session, template_id: int) -> int:
    """Return the next display_order for a template (current max + 1, or 0 if none)."""
    result = db.execute(
        select(func.max(TemplateField.display_order)).where(
            TemplateField.template_id == template_id
        )
    )
    current_max = result.scalar()
    return 0 if current_max is None else current_max + 1


def append_field(
    db: Session,
    template_id: int,
    field: TemplateFieldCreate,
) -> TemplateField | None:
    """
    Append one field to a template, idempotently.

    Returns None (skips, no duplicate) if the template already has a field
    with the same key (uq_template_field_key / field_exists guard).
    display_order defaults to next_display_order when not provided.
    """
    if field_exists(db, template_id, field.field_name):
        return None
    payload = field.model_dump()
    if payload.get("display_order") in (None, 0):
        payload["display_order"] = next_display_order(db, template_id)
    db_obj = TemplateField(template_id=template_id, **payload)
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj
