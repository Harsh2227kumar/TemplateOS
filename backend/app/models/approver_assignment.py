"""
Approver assignments: "approver" is a job a faculty or staff member holds,
not a role. One person can hold several (e.g. HOD of CSE and Exam Cell of SIT).

- title: what the job is (HOD, Director, Class Teacher, Exam Cell, ...).
- scope: the organization / institute / department it applies to, plus an
  optional free `scope_key` for finer scopes (a class such as "2024-28-A",
  or an activity such as "hackathon").
- valid_from / valid_to: assignments are ENDED (valid_to set), never deleted,
  so the history of who approved what stays intact. valid_to NULL = current.

Mirror of EkLink (SYNC_CONTRACT.md section 6): rows with source "eklink"
are upserted by `eklink_id` (EkLink's job id) from sync events and cannot be
changed here; rows with source "local" were created in TemplateOS.

Rules (app/services/approver_assignments.py): the assignee must be an
active user whose member_type is faculty or staff, inside the scope.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

APPROVER_TITLES = (
    "HOD",
    "Director",
    "Dean",
    "Class Teacher",
    "Mentor",
    "Course Faculty",
    "Exam Cell",
    "Admin Staff",
    "Event In-charge",
    "Other",
)
SCOPE_LEVELS = ("organization", "institute", "department")
SOURCES = ("local", "eklink")


class ApproverAssignment(Base):
    __tablename__ = "approver_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_level: Mapped[str] = mapped_column(String(20), nullable=False)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    institute_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("institutes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    department_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    scope_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    eklink_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    source: Mapped[str] = mapped_column(
        String(10), default="local", server_default="local", nullable=False
    )

    @property
    def managed_by_eklink(self) -> bool:
        return self.source == "eklink"

    user = relationship("User", foreign_keys=[user_id], lazy="selectin")
    organization = relationship("Organization", lazy="selectin")
    institute = relationship("Institute", lazy="selectin")
    department = relationship("Department", lazy="selectin")
