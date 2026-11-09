"""
Admin scopes: the one place that knows the hierarchy

    platform (super_admin)
      └ organization (org_admin)
          └ institute (institute_admin)
              └ department (department_admin)
                  └ faculty / staff / student

An admin manages everything whose membership falls inside their scope. A
user's membership is (organization_id, institute_id, department_id); the
lower levels always lie inside the higher ones (kept consistent by
app/services/org_directory.set_user_membership).

`scope_of(user)` returns the admin's scope, or None when the user administers
nothing (member roles, or an admin whose membership is missing).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import false
from sqlalchemy.sql.elements import ColumnElement

from app.models.user import ADMIN_ROLES, LEGACY_ROLES, USER_ROLES, User

# Lower number = more power. Legacy roles rank with members.
ROLE_RANK: dict[str, int] = {
    "super_admin": 0,
    "org_admin": 1,
    "institute_admin": 2,
    "department_admin": 3,
    "faculty": 4,
    "staff": 4,
    "student": 4,
    **{role: 4 for role in LEGACY_ROLES},
}

ROLE_LABELS: dict[str, str] = {
    "super_admin": "Super admin",
    "org_admin": "Organization admin",
    "institute_admin": "Institute admin",
    "department_admin": "Department admin",
    "faculty": "Faculty",
    "staff": "Staff",
    "student": "Student",
    "approver": "Approver (legacy)",
    "normal_user": "Staff / other (legacy)",
}

# Which roles each admin may hand out (always strictly below their own).
ASSIGNABLE: dict[str, tuple[str, ...]] = {
    "super_admin": USER_ROLES,
    "org_admin": ("institute_admin", "department_admin", "faculty", "staff", "student"),
    "institute_admin": ("department_admin", "faculty", "staff", "student"),
    "department_admin": ("faculty", "staff", "student"),
}


@dataclass(frozen=True)
class Scope:
    level: str  # "platform" | "organization" | "institute" | "department"
    id: int | None


def is_admin(user: User) -> bool:
    return user.role in ADMIN_ROLES


def scope_of(user: User) -> Scope | None:
    role = user.role
    if role == "super_admin":
        return Scope("platform", None)
    if role == "org_admin" and user.organization_id is not None:
        return Scope("organization", user.organization_id)
    if role == "institute_admin" and user.institute_id is not None:
        return Scope("institute", user.institute_id)
    if role == "department_admin" and user.department_id is not None:
        return Scope("department", user.department_id)
    return None


def contains(
    scope: Scope | None,
    organization_id: int | None,
    institute_id: int | None,
    department_id: int | None,
) -> bool:
    """Does the membership (org, institute, department) fall inside `scope`?"""
    if scope is None:
        return False
    if scope.level == "platform":
        return True
    if scope.level == "organization":
        return organization_id is not None and organization_id == scope.id
    if scope.level == "institute":
        return institute_id is not None and institute_id == scope.id
    return department_id is not None and department_id == scope.id


def user_in_scope(actor: User, target: User) -> bool:
    return contains(
        scope_of(actor), target.organization_id, target.institute_id, target.department_id
    )


def user_scope_sql(actor: User) -> ColumnElement | None:
    """SQL twin of `user_in_scope` over the users table; None = everyone."""
    scope = scope_of(actor)
    if scope is None:
        return false()
    if scope.level == "platform":
        return None
    column = {
        "organization": User.organization_id,
        "institute": User.institute_id,
        "department": User.department_id,
    }[scope.level]
    return column == scope.id


def assignable_roles(actor: User) -> tuple[str, ...]:
    return ASSIGNABLE.get(actor.role, ())


def outranks(actor: User, target: User) -> bool:
    """True if `actor` sits strictly above `target` in the role ladder."""
    return ROLE_RANK.get(actor.role, 99) < ROLE_RANK.get(target.role, 99)
