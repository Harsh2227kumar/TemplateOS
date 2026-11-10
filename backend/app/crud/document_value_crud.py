"""
CRUD helpers for document_values (V1.4 Phase 2 — Member 3).

Member 2's endpoints call these:
- upsert_values            -> PUT /documents/{id}/values
- get_values_by_document   -> GET /documents/{id}/values
- delete_values_by_document -> cascade delete (called by document_crud.delete_document)
"""

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utc_now_naive

if TYPE_CHECKING:
    from app.models.document_value import DocumentValue


def _rich_text(rich_content) -> str | None:
    """rich_content as stored text (dicts are dumped compactly)."""
    if rich_content is None:
        return None
    if isinstance(rich_content, str):
        return rich_content
    from app.services.rich_text import dump

    return dump(rich_content)


def apply_value(row: "DocumentValue", val: dict, now) -> None:
    """
    Copy one saved value onto a row (V1.7 P2 fields included).

    - value_format defaults to "plain"; rich_content is only kept for "rich"
    - ai_modified true: ai_action is stored and ai_modified_at is set when the
      flag flips to true (or the action changes); false clears both
    """
    value_format = val.get("value_format") or "plain"
    row.value = val["value"]
    row.value_format = value_format
    row.rich_content = _rich_text(val.get("rich_content")) if value_format == "rich" else None
    ai_modified = bool(val.get("ai_modified"))
    ai_action = val.get("ai_action") if ai_modified else None
    if ai_modified and (not row.ai_modified or row.ai_action != ai_action or row.ai_modified_at is None):
        row.ai_modified_at = now
    elif not ai_modified:
        row.ai_modified_at = None
    row.ai_modified = ai_modified
    row.ai_action = ai_action


def upsert_values(
    db: Session, document_id: int, values: list[dict]
) -> list["DocumentValue"]:
    """
    Upsert multiple field values for a document.

    Each item is {field_name, value} plus the optional V1.7 P2 keys
    value_format ("plain" | "rich"), rich_content (normalized Tiptap JSON,
    dict or text; validated by the caller), ai_modified and ai_action (see
    apply_value).
    - If row exists (document_id, field_name), update it + updated_at.
    - If not, insert new row.
    Also bump the parent document's updated_at so "last modified" and the
    updated_at-desc dashboard ordering reflect the save.
    Commit once at the end.
    Return all upserted rows.
    """
    from app.models.document import Document
    from app.models.document_value import DocumentValue

    now = utc_now_naive()
    result = []
    for val in values:
        field_name = val["field_name"]

        existing = db.execute(
            select(DocumentValue).where(
                DocumentValue.document_id == document_id,
                DocumentValue.field_name == field_name,
            )
        ).scalar_one_or_none()

        if existing:
            apply_value(existing, val, now)
            existing.updated_at = now
            result.append(existing)
        else:
            new_val = DocumentValue(document_id=document_id, field_name=field_name)
            apply_value(new_val, val, now)
            db.add(new_val)
            result.append(new_val)

    document = db.get(Document, document_id)
    if document:
        document.updated_at = now

    db.commit()
    for r in result:
        db.refresh(r)
    return result


def get_values_by_document(db: Session, document_id: int) -> list["DocumentValue"]:
    """
    Return all values for a document (no specific order).
    """
    from app.models.document_value import DocumentValue

    result = db.execute(
        select(DocumentValue).where(DocumentValue.document_id == document_id)
    )
    return list(result.scalars().all())


def delete_values_by_document(db: Session, document_id: int) -> int:
    """
    Delete all values for a document.
    Returns the number of rows deleted.
    """
    from app.models.document_value import DocumentValue

    from sqlalchemy import delete

    result = db.execute(
        delete(DocumentValue).where(DocumentValue.document_id == document_id)
    )
    db.commit()
    return result.rowcount or 0
