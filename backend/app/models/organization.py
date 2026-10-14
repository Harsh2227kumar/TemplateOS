"""
Organizations and departments: the canonical tables behind user membership
(users.organization_id / department_id) and template audiences
(templates.scope_organization_id / scope_department_id).

- organizations.name is unique case-insensitively (unique index on lower(name)).
- departments belong to one organization (ON DELETE CASCADE) and their name is
  unique case-insensitively within it (unique index on organization_id,
  lower(name)).

Names are stored trimmed with internal whitespace collapsed (see
app/services/org_directory.py:clean_name). The legacy free-text columns
users.organization / users.department and templates.scope_organization /
scope_department are kept as denormalized copies of these names (written
whenever an id is written, rewritten on rename) so a rollback of migration
c7a1d3e5f9b2 loses nothing.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
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


Index(
    "uq_organizations_name_lower",
    func.lower(Organization.name),
    unique=True,
)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="departments"
    )


Index(
    "uq_departments_org_name_lower",
    Department.organization_id,
    func.lower(Department.name),
    unique=True,
)
