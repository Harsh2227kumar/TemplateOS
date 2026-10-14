"""
Template access rules: who may view, who may manage, and who may publish.

This module is the single source of truth for template access. The Python
predicate `user_can_view_template` and the SQL filter
`library_visibility_filter` (used by the template library listing) implement
the SAME rule and are checked against each other by a parity test
(tests/test_template_access_scopes.py). Change both together.

Organizations and departments are rows (app/models/organization.py); every
comparison below is by id: User.organization_id / department_id against
Template.scope_organization_id / scope_department_id. A NULL id never
matches anything. The legacy name columns are never read here.

View rule
---------
- super_admin sees everything; the owner always sees their own templates.
- private: owner only.
- public: everyone.
- organization: user.organization_id == template.scope_organization_id.
- department: user.department_id == template.scope_department_id. (A
  department belongs to exactly one organization and the services keep a
  user's / template's department inside its organization, so the
  organization is implied.)
- group: unchanged legacy rule (uploader's role == user's role).
- public / organization / department: a non-empty `allowed_roles` list also
  requires user.role to be in the list. Scope managers (an org_admin of the
  template's organization, a department_admin of its department) can always
  view organization / department templates.

Manage rule (`can_manage`)
--------------------------
super_admin; the owner; an org_admin whose organization_id matches
scope_organization_id (organization and department templates); a
department_admin whose department_id matches scope_department_id
(department templates).

Deleting a template stays super_admin-only (see DELETE /templates/{id}):
it is irreversible and cascades every user's documents, so it is not a
"manage" action.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.organization import Department, Organization
from app.models.template import Template
from app.models.user import USER_ROLES, User
from app.services.org_directory import (
    clean_name,
    find_department_by_name,
    find_organization_by_name,
    get_department,
    get_organization,
)

SCOPED_VISIBILITIES = ("organization", "department")
# Roles a template can be restricted to. super_admin always sees everything,
# so listing it would be meaningless.
ASSIGNABLE_ROLES = tuple(role for role in USER_ROLES if role != "super_admin")
ROLE_LABELS = {
    "org_admin": "Organization admin",
    "department_admin": "Department admin",
    "faculty": "Faculty",
    "student": "Student",
    "approver": "Approver",
    "normal_user": "Staff / other",
}
ORG_PUBLISHERS = ("super_admin", "org_admin")
DEPARTMENT_PUBLISHERS = ("super_admin", "org_admin", "department_admin")


# ── helpers ──────────────────────────────────────────────────────────


def _same_id(a: int | None, b: int | None) -> bool:
    return a is not None and a == b


def parse_allowed_roles(raw: str | None) -> list[str] | None:
    """Decode the stored JSON array for API output; None / empty / malformed -> None."""
    if raw is None or raw == "":
        return None
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(decoded, list):
        return None
    roles = [role for role in decoded if isinstance(role, str)]
    return roles or None


def serialize_allowed_roles(roles: Iterable[str] | None) -> str | None:
    """Encode roles for storage; empty -> None (meaning all roles)."""
    roles = list(roles or [])
    return json.dumps(roles) if roles else None


def _role_allowed(template: Template, role: str | None) -> bool:
    """
    Python mirror of `_sql_role_allowed`. Unrestricted iff the stored value is
    NULL, '' or '[]'; otherwise the role must appear in the stored array.
    Malformed values therefore restrict to nobody, exactly as the SQL does.
    """
    raw = template.allowed_roles
    if raw is None or raw in ("", "[]"):
        return True
    if not role:
        return False
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return False
    return isinstance(decoded, list) and role in decoded


def _sql_role_allowed(role: str | None) -> ColumnElement:
    column = Template.allowed_roles
    unrestricted = or_(column.is_(None), column == "", column == "[]")
    if not role:
        return unrestricted
    escaped = role.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return or_(unrestricted, column.like(f'%"{escaped}"%', escape="\\"))


def _department_scope_matches(user: User, template: Template) -> bool:
    return _same_id(user.department_id, template.scope_department_id)


def is_scope_manager(user: User, template: Template) -> bool:
    """org_admin / department_admin who administers the template's scope."""
    if template.visibility not in SCOPED_VISIBILITIES:
        return False
    if user.role == "org_admin":
        return _same_id(user.organization_id, template.scope_organization_id)
    if user.role == "department_admin" and template.visibility == "department":
        return _department_scope_matches(user, template)
    return False


# ── view / manage ────────────────────────────────────────────────────


def user_can_view_template(user: User, template: Template) -> bool:
    """Return True if the user may view (and use) the template."""
    if user.role == "super_admin":
        return True
    if template.uploaded_by == user.id:
        return True

    visibility = template.visibility
    if visibility == "public":
        return _role_allowed(template, user.role)
    if visibility == "organization":
        if is_scope_manager(user, template):
            return True
        return _same_id(
            user.organization_id, template.scope_organization_id
        ) and _role_allowed(template, user.role)
    if visibility == "department":
        if is_scope_manager(user, template):
            return True
        return _department_scope_matches(user, template) and _role_allowed(
            template, user.role
        )
    if visibility == "group":
        return bool(user.role) and template.uploader.role == user.role
    return False


def can_manage(user: User, template: Template) -> bool:
    """Return True if the user may modify the template (fields, cleaning, access)."""
    if user.role == "super_admin":
        return True
    if template.uploaded_by == user.id:
        return True
    return is_scope_manager(user, template)


def library_visibility_filter(user: User) -> ColumnElement | None:
    """
    SQL twin of `user_can_view_template` for the library listing.
    Returns None when no filter applies (super_admin).
    """
    if user.role == "super_admin":
        return None

    role = user.role
    user_org = user.organization_id
    user_dept = user.department_id
    role_ok = _sql_role_allowed(role)

    conditions: list[ColumnElement] = [
        Template.uploaded_by == user.id,
        and_(Template.visibility == "public", role_ok),
    ]

    if user_org is not None:
        org_match = Template.scope_organization_id == user_org
        org_template = and_(Template.visibility == "organization", org_match)
        if role == "org_admin":
            # Scope manager: every org and department template of their org.
            conditions.append(org_template)
            conditions.append(and_(Template.visibility == "department", org_match))
        else:
            conditions.append(and_(org_template, role_ok))

    if user_dept is not None:
        dept_scope = and_(
            Template.visibility == "department",
            Template.scope_department_id == user_dept,
        )
        if role == "department_admin":
            conditions.append(dept_scope)
        else:
            conditions.append(and_(dept_scope, role_ok))

    if role:
        conditions.append(
            and_(
                Template.visibility == "group",
                Template.uploader.has(User.role == role),
            )
        )

    return or_(*conditions)


# ── publish rules ────────────────────────────────────────────────────


class PublishRuleError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class ResolvedAccess:
    visibility: str
    organization: Organization | None
    department: Department | None
    allowed_roles: str | None  # JSON text, as stored

    @property
    def scope_organization_id(self) -> int | None:
        return self.organization.id if self.organization else None

    @property
    def scope_department_id(self) -> int | None:
        return self.department.id if self.department else None


def parse_roles_csv(value: str | None) -> list[str] | None:
    """Parse the upload form's comma-separated allowed_roles."""
    if value is None:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def validate_allowed_roles(roles: Iterable[str] | None) -> list[str] | None:
    """Subset of ASSIGNABLE_ROLES, de-duplicated in canonical order; empty -> None."""
    if roles is None:
        return None
    requested = {role.strip() for role in roles if role and role.strip()}
    invalid = sorted(requested - set(ASSIGNABLE_ROLES))
    if invalid:
        raise PublishRuleError(
            422,
            f"Invalid role(s) in allowed_roles: {', '.join(invalid)}. "
            f"Allowed: {', '.join(ASSIGNABLE_ROLES)}",
        )
    ordered = [role for role in ASSIGNABLE_ROLES if role in requested]
    return ordered or None


def _lookup_organization(
    db: Session, organization_id: int | None, organization_name: str | None
) -> Organization | None:
    """Explicit organization from an id or (fallback) a case-insensitive name."""
    if organization_id is not None:
        organization = get_organization(db, organization_id)
        if organization is None:
            raise PublishRuleError(422, f"Organization {organization_id} does not exist")
        return organization
    if clean_name(organization_name) is not None:
        organization = find_organization_by_name(db, organization_name)
        if organization is None:
            raise PublishRuleError(
                422, f"Unknown organization '{clean_name(organization_name)}'"
            )
        return organization
    return None


def _lookup_department(
    db: Session,
    department_id: int | None,
    department_name: str | None,
    organization: Organization | None,
) -> Department | None:
    """Explicit department from an id or (fallback) a name inside `organization`."""
    if department_id is not None:
        department = get_department(db, department_id)
        if department is None:
            raise PublishRuleError(422, f"Department {department_id} does not exist")
        return department
    if clean_name(department_name) is not None:
        department = (
            find_department_by_name(db, organization.id, department_name)
            if organization is not None
            else None
        )
        if department is None:
            raise PublishRuleError(
                422, f"Unknown department '{clean_name(department_name)}'"
            )
        return department
    return None


def resolve_publish_access(
    db: Session,
    user: User,
    visibility: str,
    scope_organization_id: int | None = None,
    scope_department_id: int | None = None,
    allowed_roles: Iterable[str] | None = None,
    *,
    scope_organization_name: str | None = None,
    scope_department_name: str | None = None,
) -> ResolvedAccess:
    """
    Apply the publish rules for `user` and return the values to store.
    Raises PublishRuleError (403 / 422) with a user-facing message.

    Ids win; the *_name arguments are a case-insensitive fallback for older
    clients and must name an existing row.

    - organization / department visibility: super_admin, org_admin,
      department_admin only (department_admin: department visibility only).
    - org_admin: organization forced to their own (a different explicit
      organization -> 403); a department must belong to it (else 403).
    - department_admin: scope forced to their own department and its
      organization (a different explicit value -> 403).
    - super_admin: must name an organization (or, for department visibility,
      a department, whose organization is then used).
    - department visibility needs a department of the scope organization.
    - private / public / group: scope cleared; allowed_roles kept for public
      only (it has no meaning for private / group).
    """
    roles = validate_allowed_roles(allowed_roles)

    if visibility not in SCOPED_VISIBILITIES:
        return ResolvedAccess(
            visibility=visibility,
            organization=None,
            department=None,
            allowed_roles=(
                serialize_allowed_roles(roles) if visibility == "public" else None
            ),
        )

    publishers = ORG_PUBLISHERS if visibility == "organization" else DEPARTMENT_PUBLISHERS
    if user.role not in publishers:
        if visibility == "organization" and user.role == "department_admin":
            raise PublishRuleError(
                403,
                "Department admins can publish to their department only, "
                "not to the whole organization",
            )
        target = "an organization" if visibility == "organization" else "a department"
        raise PublishRuleError(
            403, f"Only administrators can publish templates to {target}"
        )

    explicit_org = _lookup_organization(db, scope_organization_id, scope_organization_name)

    if user.role == "org_admin":
        own_org = (
            get_organization(db, user.organization_id)
            if user.organization_id is not None
            else None
        )
        if own_org is None:
            raise PublishRuleError(
                422, "Your profile has no organization; ask an administrator to set it"
            )
        if explicit_org is not None and explicit_org.id != own_org.id:
            raise PublishRuleError(
                403, f"You can only publish to your own organization ({own_org.name})"
            )
        org = own_org
        dept = _lookup_department(db, scope_department_id, scope_department_name, org)
        if dept is not None and dept.organization_id != org.id:
            raise PublishRuleError(
                403,
                "You can only publish to departments of your own organization "
                f"({own_org.name})",
            )
    elif user.role == "department_admin":
        own_dept = (
            get_department(db, user.department_id)
            if user.department_id is not None
            else None
        )
        if own_dept is None:
            raise PublishRuleError(
                422, "Your profile has no department; ask an administrator to set it"
            )
        own_dept_org = own_dept.organization
        if explicit_org is not None and explicit_org.id != own_dept_org.id:
            raise PublishRuleError(
                403,
                f"You can only publish to your own organization ({own_dept_org.name})",
            )
        explicit_dept = _lookup_department(
            db, scope_department_id, scope_department_name, own_dept_org
        )
        if explicit_dept is not None and explicit_dept.id != own_dept.id:
            raise PublishRuleError(
                403, f"You can only publish to your own department ({own_dept.name})"
            )
        org = own_dept_org
        dept = own_dept
    else:  # super_admin
        org = explicit_org
        dept = _lookup_department(db, scope_department_id, scope_department_name, org)
        if org is None and dept is not None and visibility == "department":
            org = dept.organization
        if org is None:
            raise PublishRuleError(
                422,
                "scope_organization_id is required for organization/department "
                "visibility",
            )
        if dept is not None and dept.organization_id != org.id:
            raise PublishRuleError(
                422,
                f"Department '{dept.name}' does not belong to organization "
                f"'{org.name}'",
            )

    if visibility == "department":
        if dept is None:
            raise PublishRuleError(
                422, "scope_department_id is required for department visibility"
            )
    else:
        dept = None

    return ResolvedAccess(
        visibility=visibility,
        organization=org,
        department=dept,
        allowed_roles=serialize_allowed_roles(roles),
    )
