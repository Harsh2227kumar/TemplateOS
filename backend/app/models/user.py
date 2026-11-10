from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.template import Template
    from app.models.document import Document
    from app.models.organization import Department, Institute, Organization

# The platform roles, highest first. Admin roles administer a scope
# (platform > organization > institute > department); the last three are
# member roles. "Approver" is not a role: any faculty or staff member can hold
# approver assignments (app/models/approver_assignment.py).
USER_ROLES = (
    "super_admin",
    "org_admin",
    "institute_admin",
    "department_admin",
    "faculty",
    "staff",
    "student",
)
ADMIN_ROLES = ("super_admin", "org_admin", "institute_admin", "department_admin")
MEMBER_TYPES = ("faculty", "staff", "student")
# Roles from before the institute model. Rows that still carry them stay
# valid (nothing breaks) but they can no longer be assigned; the data
# migration converts them (approver -> staff + assignment, normal_user -> staff).
LEGACY_ROLES = ("approver", "normal_user")
STORED_ROLES = USER_ROLES + LEGACY_ROLES


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="student")
    # Shared identity with EkLink: the PRN / staff ID and EkLink's user id.
    # NULL for local (password) accounts such as the demo users.
    login_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    eklink_sub: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    # What the person is, independent of any admin role they hold
    # (faculty | staff | student). Approver assignments require faculty/staff.
    member_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Deactivated users cannot sign in; their documents are kept.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    # Demo accounts (kept apart from real data in reports).
    is_demo: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    batch: Mapped[str | None] = mapped_column(String(20), nullable=True)
    section: Mapped[str | None] = mapped_column(String(10), nullable=True)
    semester: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # Nullable only to keep the migration safe for any users created before auth existed.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Legacy free-text copies of the linked names (see app/models/organization.py).
    # Access rules use organization_id / department_id only.
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organization_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    department_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    institute_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("institutes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    signature_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    preferences: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    @validates("role")
    def validate_role(self, _key: str, role: str) -> str:
        if role not in STORED_ROLES:
            raise ValueError(f"Unsupported user role: {role}")
        return role

    @validates("member_type")
    def validate_member_type(self, _key: str, value: str | None) -> str | None:
        if value is not None and value not in MEMBER_TYPES:
            raise ValueError(f"Unsupported member type: {value}")
        return value

    organization_ref: Mapped["Organization | None"] = relationship(
        "Organization", foreign_keys=[organization_id], lazy="selectin"
    )
    institute_ref: Mapped["Institute | None"] = relationship(
        "Institute", foreign_keys=[institute_id], lazy="selectin"
    )
    department_ref: Mapped["Department | None"] = relationship(
        "Department", foreign_keys=[department_id], lazy="selectin"
    )

    @property
    def is_admin(self) -> bool:
        return self.role in ADMIN_ROLES

    @property
    def managed_by_eklink(self) -> bool:
        """Linked to EkLink: identity, placement, member type and the active
        flag come from EkLink (SYNC_CONTRACT.md section 7)."""
        return bool(self.eklink_sub)

    @property
    def sso(self) -> bool:
        """True for accounts without a local password (they sign in via EkLink)."""
        return self.hashed_password is None

    @property
    def institute_name(self) -> str | None:
        return self.institute_ref.name if self.institute_ref else None

    @property
    def organization_name(self) -> str | None:
        return self.organization_ref.name if self.organization_ref else None

    @property
    def department_name(self) -> str | None:
        return self.department_ref.name if self.department_ref else None

    templates: Mapped[list["Template"]] = relationship(
        "Template", back_populates="uploader"
    )
    # The DB FK is ON DELETE CASCADE; passive_deletes lets the database remove
    # documents instead of the ORM trying to NULL a NOT NULL created_by.
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="creator",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
