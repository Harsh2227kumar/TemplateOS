"""
Organizations and departments: the canonical tables behind user membership
(users.organization_id / department_id) and template audiences
(templates.scope_organization_id / scope_department_id).

- organizations.name is unique case-insensitively (unique index on lower(name)).
- institutes belong to one organization; departments belong to one
  institute (and keep organization_id = that institute's organization).
  Department names are unique case-insensitively within their institute.
- Every level has a short `code` shared with EkLink (SIU / SIT / CSE) and an
  `is_active` flag: rows are deactivated, never deleted while in use.
- A row WITH a code is mirrored from EkLink (app/services/eklink_sync.py)
  and read-only in TemplateOS (`managed_by_eklink`); rows without a code are
  local and stay editable. `is_demo` marks the demo directory.

Names are stored trimmed with internal whitespace collapsed (see
app/services/org_directory.py:clean_name). The legacy free-text columns
users.organization / users.department and templates.scope_organization /
scope_department are kept as denormalized copies of these names (written
whenever an id is written, rewritten on rename) so a rollback of migration
c7a1d3e5f9b2 loses nothing.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Organization(Base):
    """A top-level customer of the platform, e.g. a university (SIU, IIT)."""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Short stable code shared with EkLink (e.g. "SIU"); matched on SSO login.
    code: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    is_demo: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    @property
    def managed_by_eklink(self) -> bool:
        """Rows with a code come from EkLink and are read-only here."""
        return self.code is not None
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # ORM-side cascade too, so deleting an organization removes its
    # departments even on SQLite connections without PRAGMA foreign_keys.
    departments: Mapped[list["Department"]] = relationship(
        "Department",
        back_populates="organization",
        cascade="all, delete-orphan",
        order_by="Department.name",
    )
    institutes: Mapped[list["Institute"]] = relationship(
        "Institute",
        back_populates="organization",
        cascade="all, delete-orphan",
        order_by="Institute.name",
    )


Index(
    "uq_organizations_name_lower",
    func.lower(Organization.name),
    unique=True,
)


class Institute(Base):
    """An institute inside an organization (e.g. SIT inside SIU)."""

    __tablename__ = "institutes"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    is_demo: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    @property
    def managed_by_eklink(self) -> bool:
        """Rows with a code come from EkLink and are read-only here."""
        return self.code is not None
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="institutes"
    )
    departments: Mapped[list["Department"]] = relationship(
        "Department", back_populates="institute", order_by="Department.name"
    )


Index(
    "uq_institutes_org_name_lower",
    Institute.organization_id,
    func.lower(Institute.name),
    unique=True,
)
Index("uq_institutes_org_code", Institute.organization_id, Institute.code, unique=True)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable only for rows created before institutes existed; the
    # migration attaches every department to an institute and the services
    # require one for new departments.
    institute_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("institutes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    is_demo: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    @property
    def managed_by_eklink(self) -> bool:
        """Rows with a code come from EkLink and are read-only here."""
        return self.code is not None
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="departments"
    )
    institute: Mapped["Institute | None"] = relationship(
        "Institute", back_populates="departments"
    )


# Department names are unique inside their institute (two institutes of the
# same organization may both have a "Computer Science" department).
Index(
    "uq_departments_institute_name_lower",
    Department.institute_id,
    func.lower(Department.name),
    unique=True,
)
Index("uq_departments_institute_code", Department.institute_id, Department.code, unique=True)
