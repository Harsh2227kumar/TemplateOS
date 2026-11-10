"""
CRUD helpers for documents (V1.4 Phase 2 — Member 3).

Member 2's endpoints call these:
- create_document          -> POST /documents/create
- get_document_by_id       -> GET /documents/{id} (with/without values)
- get_documents_by_user    -> GET /documents (user's drafts)
- update_document_status   -> status transitions
- delete_document          -> DELETE /documents/{id}
- get_document_for_preview -> GET /documents/{id}/preview (V1.7)
"""

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, lazyload, selectinload

from app.core.clock import utc_now_naive
from app.models.document import Document, DOCUMENT_STATUSES
from app.models.template import Template

if TYPE_CHECKING:
    from app.models.document_value import DocumentValue


def create_document(
    db: Session,
    template_id: int,
    created_by: int,
    name: str | None = None,
    status: str = "draft",
) -> Document:
    """
    Insert a new document row.
    Status defaults to 'draft'.
    """
    if status not in DOCUMENT_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    db_obj = Document(
        template_id=template_id,
        created_by=created_by,
        name=name,
        status=status,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def get_document_by_id(
    db: Session, document_id: int, include_values: bool = False
) -> Document | None:
    """Return Document or None. If include_values, eagerly load .values."""
    query = select(Document).where(Document.id == document_id)
    if include_values:
        query = query.options(joinedload(Document.values))
    result = db.execute(query)
    return result.unique().scalar_one_or_none()


def get_documents_by_user(db: Session, user_id: int) -> list[Document]:
    """
    Return all documents created by the given user, newest first (by updated_at).
    """
    result = db.execute(
        select(Document)
        .where(Document.created_by == user_id)
        .order_by(Document.updated_at.desc())
    )
    return list(result.scalars().all())


def update_document_status(
    db: Session, document_id: int, status: str
) -> Document | None:
    """
    Update a document's status.
    Returns the updated Document or None if not found.
    """
    if status not in DOCUMENT_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    document = db.get(Document, document_id)
    if document:
        document.status = status
        document.updated_at = utc_now_naive()
        db.commit()
        db.refresh(document)
    return document


def delete_document(db: Session, document_id: int) -> bool:
    """
    Delete a document by ID.
    Cascade deletes its values via relationship.
    Returns True if deleted, False if not found.
    """
    document = db.get(Document, document_id)
    if document:
        db.delete(document)
        db.commit()
        return True
    return False


def get_document_for_preview(db: Session, document_id: int) -> Document | None:
    """
    Load everything GET /documents/{id}/preview needs in one round trip
    (V1.7 Phase 1): the document, its template, the template's fields, the
    saved values and the generated-file row.

    Statements: 1 (document + template + generated_file, joined) + 1 (values)
    + 1 (fields) = 3. The template's audience refs (scope organization /
    department, lazy="selectin" on the model) are deferred to lazy loading:
    the preview never reads them, and loading them eagerly would add up to
    two more statements.

    Fields come back unordered; build_sections() sorts them by
    (display_order, id). No owner filter here: the endpoint checks access.
    """
    query = (
        select(Document)
        .where(Document.id == document_id)
        .options(
            selectinload(Document.values),
            joinedload(Document.template).selectinload(Template.fields),
            joinedload(Document.template).lazyload(Template.scope_organization_ref),
            joinedload(Document.template).lazyload(Template.scope_department_ref),
            joinedload(Document.generated_file),
        )
    )
    return db.execute(query).unique().scalar_one_or_none()
