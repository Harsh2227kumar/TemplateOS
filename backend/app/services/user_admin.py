"""
User management rules (who may see / change which users). Every rule is
enforced here, server-side; the endpoints in app/api/v1/endpoints/admin.py
only translate UserAdminError into HTTP errors. Scopes come from
app/services/scopes.py:

    super_admin       everyone
    org_admin         users of their organization
    institute_admin   users of their institute
    department_admin  users of their department
    everyone else     403
An admin whose own membership is missing sees nobody but themselves.

Changes (PATCH /admin/users/{id}) - `apply_user_update`:
- The target must be visible to the actor (else 403).
- Except on themselves, an actor may only modify users whose CURRENT role
  they could assign (legacy roles count as members), i.e. users strictly
  below them. Nobody can change their own role or deactivate themselves.
- Roles an actor may assign:
    super_admin       every role
    org_admin         institute_admin, department_admin, faculty, staff, student
    institute_admin   department_admin, faculty, staff, student
    department_admin  faculty, staff, student
  Legacy roles (approver, normal_user) can no longer be assigned.
- The last active super_admin can never lose that role or be deactivated.
- Placement: organization changes are super_admin only; institute changes
  super_admin / org_admin (inside their organization); department changes
  super_admin / org_admin / institute_admin (inside their scope). The
  department must belong to the institute, the institute to the organization.
- A resulting org_admin needs an organization, institute_admin an institute
  and department_admin a department (else 422).
- member_type follows a member role (faculty/staff/student); for admins it
  can be set explicitly.
- is_active=false deactivates (the user can no longer sign in; nothing is
  deleted).
- EkLink-linked users (eklink_sub set, SYNC_CONTRACT.md section 7):
  organization / institute / department, member_type and is_active come
  from EkLink, so changing them here is 409 "Managed in EkLink". Their role
  may still be set to a TemplateOS admin role, or back to their EkLink member
  type; any other member role is 409 too (member roles come from EkLink).
  Sending the current value of a managed field is not a change.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import false, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.organization import Department, Institute, Organization
from app.models.user import ADMIN_ROLES, LEGACY_ROLES, MEMBER_TYPES, USER_ROLES, User
from app.services import scopes
from app.services.org_directory import set_user_membership

USER_ADMIN_ROLES = ADMIN_ROLES
EKLINK_MANAGED_USER_FIELDS = (
    "organization_id",
    "institute_id",
    "department_id",
    "member_type",
    "is_active",
)
MANAGED_IN_EKLINK = "Managed in EkLink"


class UserAdminError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def is_user_admin(user: User) -> bool:
    return user.role in USER_ADMIN_ROLES


def assignable_roles(actor: User) -> tuple[str, ...]:
    return scopes.assignable_roles(actor)


def require_user_admin(actor: User) -> None:
    if not is_user_admin(actor):
        raise UserAdminError(403, "Only administrators can manage users")


def user_scope_filter(actor: User) -> ColumnElement | None:
    """SQL twin of `can_see_user`; None = no restriction (super_admin)."""
    if not is_user_admin(actor):
        return false()
    if scopes.scope_of(actor) is None:
        return User.id == actor.id
    return scopes.user_scope_sql(actor)


def can_see_user(actor: User, target: User) -> bool:
    if not is_user_admin(actor):
        return False
    if actor.id == target.id:
        return True
    return scopes.user_in_scope(actor, target)


def _can_modify_role(actor: User, role: str) -> bool:
    allowed = assignable_roles(actor)
    if role in LEGACY_ROLES:
        return "staff" in allowed
    return role in allowed


_SCOPE_MESSAGES = {
    "org_admin": "You can only manage users in your own organization",
    "institute_admin": "You can only manage users in your own institute",
    "department_admin": "You can only manage users in your own department",
}


def _scope_message(actor: User) -> str:
    return _SCOPE_MESSAGES.get(actor.role, "You cannot manage this user")


def count_active_super_admins(db: Session) -> int:
    return db.scalar(
        select(func.count(User.id)).where(
            User.role == "super_admin", User.is_active.is_(True)
        )
    ) or 0


def _resolve_placement(
    db: Session, actor: User, target: User, changes: Mapping[str, Any]
) -> tuple[Organization | None, Institute | None, Department | None]:
    organization = target.organization_ref
    institute = target.institute_ref
    department = target.department_ref

    # ── organization ──
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

    # ── institute ──
    if "institute_id" in changes:
        new_inst_id = changes["institute_id"]
    elif org_changed:
        new_inst_id = None  # the old institute belonged to the old organization
    else:
        new_inst_id = target.institute_id
    inst_changed = new_inst_id != target.institute_id
    if inst_changed:
        if actor.role not in ("super_admin", "org_admin"):
            raise UserAdminError(
                403, "Only super admins and organization admins can move users between institutes"
            )
        institute = None
        if new_inst_id is not None:
            institute = db.get(Institute, new_inst_id)
            if institute is None:
                raise UserAdminError(422, f"Institute {new_inst_id} does not exist")
            if actor.role == "org_admin" and institute.organization_id != actor.organization_id:
                raise UserAdminError(
                    403, "You can only assign institutes of your own organization"
                )

    # ── department ──
    if "department_id" in changes:
        new_dept_id = changes["department_id"]
    elif org_changed or inst_changed:
        # keep the department only if it still lies inside the new placement
        keep = (
            department is not None
            and (institute is None or department.institute_id == (institute.id if institute else None))
            and (organization is not None and department.organization_id == organization.id)
        )
        new_dept_id = target.department_id if keep else None
    else:
        new_dept_id = target.department_id
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
            if actor.role == "org_admin" and department.organization_id != actor.organization_id:
                raise UserAdminError(
                    403, "You can only assign departments of your own organization"
                )
            if actor.role == "institute_admin" and department.institute_id != actor.institute_id:
                raise UserAdminError(
                    403, "You can only assign departments of your own institute"
                )
    elif department is not None and inst_changed and institute is not None:
        if department.institute_id != institute.id:
            department = None

    if department is not None and (
        organization is None or department.organization_id != organization.id
    ):
        raise UserAdminError(
            422,
            f"Department '{department.name}' does not belong to the user's organization",
        )
    if department is not None and department.institute_id is not None:
        if institute is not None and institute.id != department.institute_id:
            raise UserAdminError(
                422,
                f"Department '{department.name}' does not belong to the user's institute",
            )
        institute = department.institute
    if institute is not None and (
        organization is None or institute.organization_id != organization.id
    ):
        raise UserAdminError(
            422, f"Institute '{institute.name}' does not belong to the user's organization"
        )
    return organization, institute, department


def check_eklink_ownership(target: User, changes: Mapping[str, Any]) -> None:
    """409 for changes to fields EkLink owns on a linked user."""
    if not target.eklink_sub:
        return
    changed = [
        key
        for key in EKLINK_MANAGED_USER_FIELDS
        if key in changes and changes[key] != getattr(target, key)
    ]
    if changed:
        raise UserAdminError(
            409, f"{MANAGED_IN_EKLINK}: {', '.join(changed)} can only be changed in EkLink"
        )
    role = changes.get("role")
    if (
        role is not None
        and role != target.role
        and role not in ADMIN_ROLES
        and role != target.member_type
    ):
        raise UserAdminError(
            409,
            f"{MANAGED_IN_EKLINK}: member roles come from EkLink "
            f"(this user is '{target.member_type or 'no member type'}')",
        )


def apply_user_update(
    db: Session, actor: User, target: User, changes: Mapping[str, Any]
) -> None:
    """
    Validate `changes` (keys: role, organization_id, institute_id,
    department_id, member_type, is_active; only the keys present are applied)
    for `actor` and apply them to `target`. Raises UserAdminError (403 / 422).
    Does not commit.
    """
    require_user_admin(actor)
    if not can_see_user(actor, target):
        raise UserAdminError(403, _scope_message(actor))

    is_self = actor.id == target.id
    if not is_self and not _can_modify_role(actor, target.role):
        raise UserAdminError(
            403, f"You cannot modify a user with the role '{target.role}'"
        )
    check_eklink_ownership(target, changes)

    # ── role ──
    new_role = target.role
    if "role" in changes and changes["role"] != target.role:
        new_role = changes["role"]
        if new_role not in USER_ROLES:
            raise UserAdminError(422, f"Unknown role '{new_role}'")
        if is_self:
            raise UserAdminError(403, "You cannot change your own role")
        if new_role not in assignable_roles(actor):
            raise UserAdminError(403, f"You cannot assign the role '{new_role}'")
        if target.role == "super_admin" and count_active_super_admins(db) <= 1:
            raise UserAdminError(422, "Cannot remove the last super admin")

    # ── active flag ──
    new_active = target.is_active
    if "is_active" in changes and changes["is_active"] != target.is_active:
        new_active = bool(changes["is_active"])
        if is_self:
            raise UserAdminError(403, "You cannot deactivate yourself")
        if (
            not new_active
            and target.role == "super_admin"
            and count_active_super_admins(db) <= 1
        ):
            raise UserAdminError(422, "Cannot deactivate the last super admin")

    organization, institute, department = _resolve_placement(db, actor, target, changes)

    if new_role == "org_admin" and organization is None:
        raise UserAdminError(422, "An organization admin needs an organization")
    if new_role == "institute_admin" and institute is None:
        raise UserAdminError(422, "An institute admin needs an institute")
    if new_role == "department_admin" and department is None:
        raise UserAdminError(422, "A department admin needs a department")

    # ── member type ──
    member_type = target.member_type
    if "member_type" in changes:
        member_type = changes["member_type"]
        if member_type is not None and member_type not in MEMBER_TYPES:
            raise UserAdminError(422, f"Unknown member type '{member_type}'")
    if new_role in MEMBER_TYPES:
        member_type = new_role

    target.role = new_role
    target.member_type = member_type
    target.is_active = new_active
    set_user_membership(target, organization, department, institute)
