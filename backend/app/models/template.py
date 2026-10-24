"""
Template model.
IMPORTANT: original_file_path and processed_file_path store only
relative file paths. Never store DOCX or PDF binary data here.
All files live on disk under backend/storage/.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.template_field import TemplateField
    from app.models.document import Document
    from app.models.organization import Department, Organization
    from app.models.template_revision import TemplateRevision

TEMPLATE_CATEGORIES = (
    "notice",
    "mom",
    "report",
    "application",
    "letter",
    "certificate",
    "proposal",
    "invoice",
    "custom",
)
TEMPLATE_VISIBILITY = ("private", "public", "organization", "department", "group")
TEMPLATE_STATUSES = (
    "uploaded",
    "placeholder_detected",
    "field_configured",
    "active",
    "archived",
    "locked",
)


class Template(Base):
    __tablename__ = "templates"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "status" not in kwargs:
            self.status = "uploaded"
        if "version" not in kwargs:
            self.version = 1
        if "is_locked" not in kwargs:
            self.is_locked = False

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    visibility: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), default="uploaded", server_default="uploaded", index=True
    )

    # File metadata — paths only, never binary
    original_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    processed_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_extension: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Ownership
    uploaded_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    organization_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    department_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Audience (see app/services/template_access.py): matched by id against
    # User.organization_id / department_id.
    scope_organization_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scope_department_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Legacy free-text copies of the linked names, kept in sync for rollback
    # safety; never used for access decisions.
    scope_organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scope_department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # JSON array of role strings; NULL / empty array = every role.
    allowed_roles: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Flags
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # V1.7 P2.1: a user's personal copy ("Customize for me") points at the
    # template it was copied from; the original is never changed by them.
    parent_template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("templates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_locked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    uploader: Mapped["User"] = relationship("User", back_populates="templates")
    scope_organization_ref: Mapped["Organization | None"] = relationship(
        "Organization", foreign_keys=[scope_organization_id], lazy="selectin"
    )
    scope_department_ref: Mapped["Department | None"] = relationship(
        "Department", foreign_keys=[scope_department_id], lazy="selectin"
    )

    parent: Mapped["Template | None"] = relationship(
        "Template", remote_side="Template.id", foreign_keys=[parent_template_id]
    )
    # V1.7 P2.1: every file change, newest first. Deleted through the ORM so
    # their stored files are removed (app.services.generated_file_cleanup).
    revisions: Mapped[list["TemplateRevision"]] = relationship(
        "TemplateRevision",
        back_populates="template",
        order_by="TemplateRevision.revision.desc()",
        cascade="all, delete-orphan",
    )

    @property
    def parent_template_name(self) -> str | None:
        return self.parent.name if self.parent is not None else None

    @property
    def is_personal_copy(self) -> bool:
        return self.parent_template_id is not None

    @property
    def scope_organization_name(self) -> str | None:
        ref = self.scope_organization_ref
        return ref.name if ref else None

    @property
    def scope_department_name(self) -> str | None:
        ref = self.scope_department_ref
        return ref.name if ref else None
    fields: Mapped[list["TemplateField"]] = relationship(
        "TemplateField", back_populates="template", cascade="all, delete-orphan"
    )
    # The DB FK is ON DELETE CASCADE; passive_deletes lets the database remove
    # documents instead of the ORM trying to NULL a NOT NULL template_id.
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="template",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @validates("category")
    def validate_category(self, _key: str, category: str) -> str:
        if category not in TEMPLATE_CATEGORIES:
            raise ValueError(f"Unsupported template category: {category}")
        return category

    @validates("visibility")
    def validate_visibility(self, _key: str, visibility: str) -> str:
        if visibility not in TEMPLATE_VISIBILITY:
            raise ValueError(f"Unsupported template visibility: {visibility}")
        return visibility

    @validates("status")
    def validate_status(self, _key: str, status: str) -> str:
        if status not in TEMPLATE_STATUSES:
            raise ValueError(f"Unsupported template status: {status}")
        return status
