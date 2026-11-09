"""
Template access rules: who may view, who may manage, and who may publish.

This module is the single source of truth for template access. The Python
predicate `user_can_view_template` and the SQL filter
`library_visibility_filter` (used by the template library listing) implement
the SAME rule and are checked against each other by a parity test
(tests/test_template_access_scopes.py). Change both together.

Organizations, institutes and departments are rows
(app/models/organization.py); every comparison below is by id:
User.organization_id / institute_id / department_id against
Template.scope_organization_id / scope_institute_id / scope_department_id.
A NULL id never matches anything. The legacy name columns are never read.

View rule
---------
- super_admin sees everything; the owner always sees their own templates.
- private: owner only.
- public: everyone.
- organization: user.organization_id == template.scope_organization_id.
- institute: user.institute_id == template.scope_institute_id.
- department: user.department_id == template.scope_department_id.
- group: unchanged legacy rule (uploader's role == user's role).
- public / organization / institute / department: a non-empty
  `allowed_roles` list also requires user.role to be in the list. Scope
  managers (below) can always view the templates they manage.

Manage rule (`can_manage`)
--------------------------
super_admin; the owner; a scope manager: an admin whose scope
(app/services/scopes.py) contains the template's scope AND is at the same
level or above it. So an org_admin manages every organization / institute /
department template of their organization, an institute_admin the institute
and department templates of their institute, a department_admin the
department templates of their department.

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

from app.models.organization import Department, Institute, Organization
from app.models.template import Template
from app.models.user import USER_ROLES, User
from app.services import scopes
from app.services.org_directory import (
    clean_name,
    find_department_by_name,
    find_institute_by_name,
    find_organization_by_name,
    get_department,
    get_institute,
    get_organization,
)

SCOPED_VISIBILITIES = ("organization", "institute", "department")
# Roles a template can be restricted to. super_admin always sees everything,
# so listing it would be meaningless.
ASSIGNABLE_ROLES = tuple(role for role in USER_ROLES if role != "super_admin")
ROLE_LABELS = {role: scopes.ROLE_LABELS[role] for role in ASSIGNABLE_ROLES}
ORG_PUBLISHERS = ("super_admin", "org_admin")
INSTITUTE_PUBLISHERS = ("super_admin", "org_admin", "institute_admin")
DEPARTMENT_PUBLISHERS = ("super_admin", "org_admin", "institute_admin", "department_admin")
PUBLISHERS = {
    "organization": ORG_PUBLISHERS,
    "institute": INSTITUTE_PUBLISHERS,
    "department": DEPARTMENT_PUBLISHERS,
}
# Visibility level -> how deep it sits (lower = wider).
_LEVEL_RANK = {"platform": 0, "organization": 1, "institute": 2, "department": 3}


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


def is_scope_manager(user: User, template: Template) -> bool:
    """An admin whose scope contains the template's scope, at or above its level."""
    if template.visibility not in SCOPED_VISIBILITIES:
        return False
    scope = scopes.scope_of(user)
    if scope is None or scope.level == "platform":
        return False
    if _LEVEL_RANK[scope.level] > _LEVEL_RANK[template.visibility]:
        return False
    return scopes.contains(
        scope,
        template.scope_organization_id,
        template.scope_institute_id,
        template.scope_department_id,
    )


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
    if visibility in SCOPED_VISIBILITIES:
        if is_scope_manager(user, template):
            return True
        member_of = {
            "organization": _same_id(user.organization_id, template.scope_organization_id),
            "institute": _same_id(user.institute_id, template.scope_institute_id),
            "department": _same_id(user.department_id, template.scope_department_id),
        }[visibility]
        return member_of and _role_allowed(template, user.role)
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


def _sql_scope_manager(user: User) -> ColumnElement | None:
    """SQL twin of `is_scope_manager`; None when the user manages no scope."""
    scope = scopes.scope_of(user)
    if scope is None or scope.level == "platform":
        return None
    if scope.level == "organization":
        return and_(
            Template.visibility.in_(SCOPED_VISIBILITIES),
            Template.scope_organization_id == scope.id,
        )
    if scope.level == "institute":
        return and_(
            Template.visibility.in_(("institute", "department")),
            Template.scope_institute_id == scope.id,
        )
    return and_(
        Template.visibility == "department",
        Template.scope_department_id == scope.id,
    )


def library_visibility_filter(user: User) -> ColumnElement | None:
    """
    SQL twin of `user_can_view_template` for the library listing.
    Returns None when no filter applies (super_admin).
    """
    if user.role == "super_admin":
        return None

    role = user.role
    role_ok = _sql_role_allowed(role)

    conditions: list[ColumnElement] = [
        Template.uploaded_by == user.id,
        and_(Template.visibility == "public", role_ok),
    ]
    manager = _sql_scope_manager(user)
    if manager is not None:
        conditions.append(manager)

    if user.organization_id is not None:
        conditions.append(
            and_(
                Template.visibility == "organization",
                Template.scope_organization_id == user.organization_id,
                role_ok,
            )
        )
    if user.institute_id is not None:
        conditions.append(
            and_(
                Template.visibility == "institute",
                Template.scope_institute_id == user.institute_id,
                role_ok,
            )
        )
    if user.department_id is not None:
        conditions.append(
            and_(
                Template.visibility == "department",
                Template.scope_department_id == user.department_id,
                role_ok,
            )
        )

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
    institute: Institute | None = None

    @property
    def scope_organization_id(self) -> int | None:
        return self.organization.id if self.organization else None

    @property
    def scope_institute_id(self) -> int | None:
        return self.institute.id if self.institute else None

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


def _lookup_institute(
    db: Session,
    institute_id: int | None,
    institute_name: str | None,
    organization: Organization | None,
) -> Institute | None:
    if institute_id is not None:
        institute = get_institute(db, institute_id)
        if institute is None:
            raise PublishRuleError(422, f"Institute {institute_id} does not exist")
        return institute
    if clean_name(institute_name) is not None:
        institute = (
            find_institute_by_name(db, organization.id, institute_name)
            if organization is not None
            else None
        )
        if institute is None:
            raise PublishRuleError(422, f"Unknown institute '{clean_name(institute_name)}'")
        return institute
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


_TARGET_WORDS = {
    "organization": "an organization",
    "institute": "an institute",
    "department": "a department",
}


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
    scope_institute_id: int | None = None,
    scope_institute_name: str | None = None,
) -> ResolvedAccess:
    """
    Apply the publish rules for `user` and return the values to store.
    Raises PublishRuleError (403 / 422) with a user-facing message.

    Ids win; the *_name arguments are a case-insensitive fallback for older
    clients and must name an existing row.

    - organization visibility: super_admin, org_admin.
    - institute visibility: super_admin, org_admin, institute_admin.
    - department visibility: those plus department_admin.
    - Non-super admins are confined to their own scope: an explicit
      organization / institute / department outside it -> 403.
    - super_admin must name the target (organization, institute or
      department; the parents are derived from the child).
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

    if user.role not in PUBLISHERS[visibility]:
        if user.role == "department_admin":
            target = (
                "the whole organization" if visibility == "organization" else "the whole institute"
            )
            raise PublishRuleError(
                403,
                f"Department admins can publish to their department only, not to {target}",
            )
        if user.role == "institute_admin":
            raise PublishRuleError(
                403,
                "Institute admins can publish to their institute or its departments only, "
                "not to the whole organization",
            )
        raise PublishRuleError(
            403, f"Only administrators can publish templates to {_TARGET_WORDS[visibility]}"
        )

    explicit_org = _lookup_organization(db, scope_organization_id, scope_organization_name)

    if user.role == "super_admin":
        org = explicit_org
        inst = _lookup_institute(db, scope_institute_id, scope_institute_name, org)
        dept = _lookup_department(db, scope_department_id, scope_department_name, org)
        if dept is not None and visibility == "department":
            if org is None:
                org = dept.organization
            if inst is None:
                inst = dept.institute
        if inst is not None and org is None:
            org = inst.organization
    else:
        own_org = get_organization(db, user.organization_id) if user.organization_id else None
        if own_org is None:
            raise PublishRuleError(
                422, "Your profile has no organization; ask an administrator to set it"
            )
        if explicit_org is not None and explicit_org.id != own_org.id:
            raise PublishRuleError(
                403, f"You can only publish to your own organization ({own_org.name})"
            )
        org = own_org
        inst = _lookup_institute(db, scope_institute_id, scope_institute_name, org)
        dept = _lookup_department(db, scope_department_id, scope_department_name, org)
        if user.role == "institute_admin":
            own_inst = get_institute(db, user.institute_id) if user.institute_id else None
            if own_inst is None:
                raise PublishRuleError(
                    422, "Your profile has no institute; ask an administrator to set it"
                )
            if inst is not None and inst.id != own_inst.id:
                raise PublishRuleError(
                    403, f"You can only publish to your own institute ({own_inst.name})"
                )
            inst = own_inst
        if user.role == "department_admin":
            own_dept = get_department(db, user.department_id) if user.department_id else None
            if own_dept is None:
                raise PublishRuleError(
                    422, "Your profile has no department; ask an administrator to set it"
                )
            if dept is not None and dept.id != own_dept.id:
                raise PublishRuleError(
                    403, f"You can only publish to your own department ({own_dept.name})"
                )
            if inst is not None and inst.id != own_dept.institute_id:
                raise PublishRuleError(
                    403, f"You can only publish to your own department ({own_dept.name})"
                )
            dept = own_dept
            inst = own_dept.institute
        if dept is not None and dept.organization_id != org.id:
            raise PublishRuleError(
                403,
                f"You can only publish to departments of your own organization ({org.name})",
            )
        if dept is not None and inst is not None and dept.institute_id not in (None, inst.id):
            raise PublishRuleError(
                403, f"Department '{dept.name}' is not part of {inst.name}"
            )
        if user.role == "institute_admin" and dept is not None and dept.institute_id != inst.id:
            raise PublishRuleError(
                403, f"You can only publish to departments of your own institute ({inst.name})"
            )

    if org is None:
        raise PublishRuleError(
            422,
            "scope_organization_id is required for organization/institute/department "
            "visibility",
        )
    if inst is not None and inst.organization_id != org.id:
        raise PublishRuleError(
            422, f"Institute '{inst.name}' does not belong to organization '{org.name}'"
        )
    if dept is not None and dept.organization_id != org.id:
        raise PublishRuleError(
            422,
            f"Department '{dept.name}' does not belong to organization '{org.name}'",
        )

    if visibility == "department":
        if dept is None:
            raise PublishRuleError(
                422, "scope_department_id is required for department visibility"
            )
        inst = dept.institute if dept.institute_id is not None else inst
    elif visibility == "institute":
        dept = None
        if inst is None:
            raise PublishRuleError(
                422, "scope_institute_id is required for institute visibility"
            )
    else:
        dept = None
        inst = None

    return ResolvedAccess(
        visibility=visibility,
        organization=org,
        department=dept,
        allowed_roles=serialize_allowed_roles(roles),
        institute=inst,
    )
