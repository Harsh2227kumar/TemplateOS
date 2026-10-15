"""
Document permissions (V1.7 Phase 1).

The single place that decides who may see a document and what they may do
with it. The preview page (and, in later phases, versions and downloads)
call these helpers instead of comparing created_by inline.

V1.7: owner only. V1.8 (approvals) extends document_permissions() and
require_document_viewer() for approvers; keep every rule here.
"""

from fastapi import HTTPException, status

from app.models.document import Document
from app.models.user import User
from app.schemas.document_preview import PreviewPermissions

# Statuses whose values may still be edited and regenerated. Later workflow
# statuses (submitted, approved, rejected, final) are read-only.
EDITABLE_STATUSES = ("draft", "generated")


def is_document_owner(user: User, document: Document) -> bool:
    return document.created_by == user.id


def document_permissions(user: User, document: Document) -> PreviewPermissions:
    """What `user` may do with `document` next."""
    owner = is_document_owner(user, document)
    editable = owner and document.status in EDITABLE_STATUSES
    return PreviewPermissions(
        can_edit=editable,
        can_generate=editable,
        can_download=owner,
    )


def require_document_viewer(user: User, document: Document) -> None:
    """403 unless `user` may view `document` (V1.7: the owner)."""
    if not is_document_owner(user, document):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only preview your own documents",
        )
