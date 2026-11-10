"""
Approver assignment rules (see app/models/approver_assignment.py).

- Managing assignments: an admin may create / end assignments whose scope
  lies inside their own admin scope (super_admin anywhere).
- The assignee must be active, have member_type faculty or staff, and belong
  to the assignment's scope (same organization / institute / department).
- Assignments are ended (valid_to = today), never deleted.
- `active_assignments_for(user)` lists what someone currently approves.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.clock import utc_now_naive
from app.models.approver_assignment import APPROVER_TITLES, SCOPE_LEVELS, ApproverAssignment
from app.models.organization import Department, Institute, Organization
from app.models.user import User
from app.services import scopes


class AssignmentError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def today() -> date:
    return utc_now_naive().date()


def is_current(assignment: ApproverAssignment, on: date | None = None) -> bool:
    on = on or today()
    return assignment.valid_from <= on and (assignment.valid_to is None or assignment.valid_to >= on)


def assignment_scope_filter(actor: User) -> ColumnElement | None:
    """Assignments visible to / manageable by `actor`; None = all."""
    scope = scopes.scope_of(actor)
    if scope is None:
        return ApproverAssignment.user_id == actor.id
    if scope.level == "platform":
        return None
    if scope.level == "organization":
        return ApproverAssignment.organization_id == scope.id
    if scope.level == "institute":
        return ApproverAssignment.institute_id == scope.id
    return ApproverAssignment.department_id == scope.id


def _resolve_scope(
    db: Session, level: str, organization_id: int | None, institute_id: int | None,
    department_id: int | None,
) -> tuple[Organization, Institute | None, Department | None]:
    if level not in SCOPE_LEVELS:
        raise AssignmentError(422, f"scope_level must be one of: {', '.join(SCOPE_LEVELS)}")
    department = institute = organization = None
    if level == "department":
        if department_id is None:
            raise AssignmentError(422, "department_id is required for a department assignment")
        department = db.get(Department, department_id)
        if department is None:
            raise AssignmentError(422, f"Department {department_id} does not exist")
        institute = department.institute
        organization = department.organization
    elif level == "institute":
        if institute_id is None:
            raise AssignmentError(422, "institute_id is required for an institute assignment")
        institute = db.get(Institute, institute_id)
        if institute is None:
            raise AssignmentError(422, f"Institute {institute_id} does not exist")
        organization = institute.organization
    else:
        if organization_id is None:
            raise AssignmentError(422, "organization_id is required for an organization assignment")
        organization = db.get(Organization, organization_id)
        if organization is None:
            raise AssignmentError(422, f"Organization {organization_id} does not exist")
    return organization, institute, department


def create_assignment(
    db: Session,
    actor: User,
    *,
    user_id: int,
    title: str,
    scope_level: str,
    organization_id: int | None = None,
    institute_id: int | None = None,
    department_id: int | None = None,
    scope_key: str | None = None,
    valid_from: date | None = None,
    valid_to: date | None = None,
) -> ApproverAssignment:
    if not scopes.is_admin(actor):
        raise AssignmentError(403, "Only administrators can assign approvers")
    title = (title or "").strip()
    if title not in APPROVER_TITLES:
        raise AssignmentError(422, f"title must be one of: {', '.join(APPROVER_TITLES)}")
    organization, institute, department = _resolve_scope(
        db, scope_level, organization_id, institute_id, department_id
    )
    actor_scope = scopes.scope_of(actor)
    if not scopes.contains(
        actor_scope, organization.id, institute.id if institute else None,
        department.id if department else None,
    ) or (
        # an institute / department admin cannot create a wider assignment
        actor_scope is not None
        and actor_scope.level in ("institute", "department")
        and scope_level == "organization"
    ) or (
        actor_scope is not None and actor_scope.level == "department" and scope_level == "institute"
    ):
        raise AssignmentError(403, "You can only assign approvers inside your own scope")

    assignee = db.get(User, user_id)
    if assignee is None:
        raise AssignmentError(422, f"User {user_id} does not exist")
    if not assignee.is_active:
        raise AssignmentError(422, "A deactivated user cannot be an approver")
    if assignee.member_type not in ("faculty", "staff"):
        raise AssignmentError(422, "Approvers must be faculty or staff members")
    target = {"organization": organization, "institute": institute, "department": department}[
        scope_level
    ]
    if not scopes.contains(
        scopes.Scope(scope_level, target.id),
        assignee.organization_id,
        assignee.institute_id,
        assignee.department_id,
    ):
        raise AssignmentError(422, "The approver must belong to the assignment's scope")

    start = valid_from or today()
    if valid_to is not None and valid_to < start:
        raise AssignmentError(422, "valid_to cannot be before valid_from")
    key = (scope_key or "").strip() or None
    if key is not None and len(key) > 64:
        raise AssignmentError(422, "scope_key must be 64 characters or fewer")

    assignment = ApproverAssignment(
        user_id=assignee.id,
        title=title,
        scope_level=scope_level,
        organization_id=organization.id,
        institute_id=institute.id if institute else None,
        department_id=department.id if department else None,
        scope_key=key,
        valid_from=start,
        valid_to=valid_to,
        created_by=actor.id,
    )
    db.add(assignment)
    db.flush()
    return assignment


def can_manage_assignment(actor: User, assignment: ApproverAssignment) -> bool:
    return scopes.contains(
        scopes.scope_of(actor), assignment.organization_id, assignment.institute_id,
        assignment.department_id,
    )


def end_assignment(db: Session, actor: User, assignment: ApproverAssignment) -> None:
    if not scopes.is_admin(actor) or not can_manage_assignment(actor, assignment):
        raise AssignmentError(403, "You can only manage approvers inside your own scope")
    if assignment.valid_to is not None and assignment.valid_to <= today():
        raise AssignmentError(409, "This assignment has already ended")
    assignment.valid_to = max(today(), assignment.valid_from)


def active_assignments_for(db: Session, user: User) -> list[ApproverAssignment]:
    on = today()
    return list(
        db.scalars(
            select(ApproverAssignment)
            .where(
                ApproverAssignment.user_id == user.id,
                ApproverAssignment.valid_from <= on,
                or_(ApproverAssignment.valid_to.is_(None), ApproverAssignment.valid_to >= on),
            )
            .order_by(ApproverAssignment.title)
        ).all()
    )


def current_filter(on: date | None = None) -> ColumnElement:
    on = on or today()
    return and_(
        ApproverAssignment.valid_from <= on,
        or_(ApproverAssignment.valid_to.is_(None), ApproverAssignment.valid_to >= on),
    )
