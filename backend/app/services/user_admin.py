"""
User management rules (who may see / change which users). Every rule is
enforced here, server-side; the endpoints in app/api/v1/endpoints/admin.py
only translate UserAdminError into HTTP errors.

Visibility (GET /admin/users) - `user_scope_filter` / `can_see_user`:
- super_admin: everyone.
- org_admin: users whose organization_id == their organization_id.
- department_admin: users whose department_id == their department_id.
- everyone else: 403.
An admin without an organization / department sees nobody but themselves.

Changes (PATCH /admin/users/{id}) - `apply_user_update`:
- The target must be visible to the actor (else 403).
- Except on themselves, an actor may only modify users whose CURRENT role
  they could assign (an org_admin cannot touch another org_admin or a
  super_admin; a department_admin cannot touch another department_admin).
- Nobody can change their own role (no self-escalation, and a super_admin
  cannot demote themselves).
- Roles an actor may assign (`assignable_roles`):
    super_admin       every role
    org_admin         department_admin, faculty, student, approver, normal_user
    department_admin  faculty, student, approver, normal_user
- The last super_admin can never lose that role (422).
- organization_id: only a super_admin may change it. Changing it clears the
  department unless a department of the new organization is given.
- department_id: super_admin any department of the user's organization;
  org_admin a department of their own organization; department_admin
  cannot change it.
- The department must belong to the user's resulting organization (422).
- A resulting org_admin needs an organization and a resulting
  department_admin needs a department (422), otherwise they would
  administer nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import false, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.organization import Department, Organization
from app.models.user import USER_ROLES, User
from app.services.org_directory import set_user_membership

USER_ADMIN_ROLES = ("super_admin", "org_admin", "department_admin")
_ASSIGNABLE: dict[str, tuple[str, ...]] = {
    "super_admin": USER_ROLES,
    "org_admin": ("department_admin", "faculty", "student", "approver", "normal_user"),
    "department_admin": ("faculty", "student", "approver", "normal_user"),
}


class UserAdminError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def is_user_admin(user: User) -> bool:
    return user.role in USER_ADMIN_ROLES


def assignable_roles(actor: User) -> tuple[str, ...]:
    return _ASSIGNABLE.get(actor.role, ())


def require_user_admin(actor: User) -> None:
    if not is_user_admin(actor):
        raise UserAdminError(403, "Only administrators can manage users")


def user_scope_filter(actor: User) -> ColumnElement | None:
    """SQL twin of `can_see_user`; None = no restriction (super_admin)."""
    if actor.role == "super_admin":
        return None
    if actor.role == "org_admin" and actor.organization_id is not None:
        return User.organization_id == actor.organization_id
    if actor.role == "department_admin" and actor.department_id is not None:
        return User.department_id == actor.department_id
    if is_user_admin(actor):
        return User.id == actor.id
    return false()


def can_see_user(actor: User, target: User) -> bool:
    if actor.role == "super_admin":
        return True
    if actor.id == target.id:
        return is_user_admin(actor)
    if actor.role == "org_admin":
        return (
            actor.organization_id is not None
            and target.organization_id == actor.organization_id
        )
    if actor.role == "department_admin":
        return (
            actor.department_id is not None
            and target.department_id == actor.department_id
        )
    return False


def _scope_message(actor: User) -> str:
    if actor.role == "org_admin":
        return "You can only manage users in your own organization"
    return "You can only manage users in your own department"


def _count_super_admins(db: Session) -> int:
    return db.scalar(
        select(func.count(User.id)).where(User.role == "super_admin")
    ) or 0


def apply_user_update(
    db: Session, actor: User, target: User, changes: Mapping[str, Any]
) -> None:
    """
    Validate `changes` (keys: role, organization_id, department_id; only the
    keys present are applied) for `actor` and apply them to `target`.
    Raises UserAdminError (403 / 422). Does not commit.
    """
    require_user_admin(actor)
    if not can_see_user(actor, target):
        raise UserAdminError(403, _scope_message(actor))

    allowed = assignable_roles(actor)
    is_self = actor.id == target.id
    if not is_self and target.role not in allowed:
        raise UserAdminError(
            403, f"You cannot modify a user with the role '{target.role}'"
        )

    # ── role ──
    new_role = target.role
    if "role" in changes and changes["role"] != target.role:
        new_role = changes["role"]
        if new_role not in USER_ROLES:
            raise UserAdminError(422, f"Unknown role '{new_role}'")
        if is_self:
            raise UserAdminError(403, "You cannot change your own role")
        if new_role not in allowed:
            raise UserAdminError(403, f"You cannot assign the role '{new_role}'")
        if target.role == "super_admin" and _count_super_admins(db) <= 1:
            raise UserAdminError(422, "Cannot remove the last super admin")

    # ── organization ──
    organization = target.organization_ref
    org_changed = (
        "organization_id" in changes
        and changes["organization_id"] != target.organization_id
    )
    if org_changed:
        if actor.role != "super_admin":
            raise UserAdminError(
                403, "Only a super admin can move users between organizations"
            )
        new_org_id = changes["organization_id"]
        organization = None
        if new_org_id is not None:
            organization = db.get(Organization, new_org_id)
            if organization is None:
                raise UserAdminError(422, f"Organization {new_org_id} does not exist")

    # ── department ──
    if "department_id" in changes:
        new_dept_id = changes["department_id"]
    elif org_changed:
        new_dept_id = None  # the old department belonged to the old organization
    else:
        new_dept_id = target.department_id

    department = target.department_ref
    if new_dept_id != target.department_id:
        if actor.role == "department_admin":
            raise UserAdminError(
                403, "Department admins cannot move users between departments"
            )
        department = None
        if new_dept_id is not None:
            department = db.get(Department, new_dept_id)
            if department is None:
                raise UserAdminError(422, f"Department {new_dept_id} does not exist")
            if (
                actor.role == "org_admin"
                and department.organization_id != actor.organization_id
            ):
                raise UserAdminError(
                    403, "You can only assign departments of your own organization"
                )

    if department is not None and (
        organization is None or department.organization_id != organization.id
    ):
        raise UserAdminError(
            422,
            f"Department '{department.name}' does not belong to the user's organization",
        )

    if new_role == "org_admin" and organization is None:
        raise UserAdminError(422, "An organization admin needs an organization")
    if new_role == "department_admin" and department is None:
        raise UserAdminError(422, "A department admin needs a department")

    target.role = new_role
    set_user_membership(target, organization, department)
