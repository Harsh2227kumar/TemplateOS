"""
Template access rules: who may view, who may manage, and who may publish.

This module is the single source of truth for template access. The Python
predicate `user_can_view_template` and the SQL filter
`library_visibility_filter` (used by the template library listing) implement
the SAME rule and are checked against each other by a parity test
(tests/test_template_access_scopes.py). Change both together.

View rule
---------
- super_admin sees everything; the owner always sees their own templates.
- private: owner only.
- public: everyone.
- organization: user's organization == template.scope_organization.
- department: user's department == template.scope_department AND, when
  scope_organization is set, user's organization == scope_organization.
- group: unchanged legacy rule (uploader's role == user's role).
- public / organization / department: a non-empty `allowed_roles` list also
  requires user.role to be in the list. Scope managers (an org_admin of the
  template's organization, a department_admin of its department) can always
  view organization / department templates.

Organization / department strings are free text, so comparisons are trimmed
and case-insensitive (Python `strip().lower()` vs SQL `lower(trim(x))`;
scope values are stored already stripped, so both sides agree for ASCII).

Manage rule (`can_manage`)
--------------------------
super_admin; the owner; an org_admin whose organization matches
scope_organization (organization and department templates); a
department_admin whose department matches scope_department (department
templates; the organization must also match when scope_organization is set).

Deleting a template stays super_admin-only (see DELETE /templates/{id}):
it is irreversible and cascades every user's documents, so it is not a
"manage" action.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import and_, false, func, or_
from sqlalchemy.sql.elements import ColumnElement

from app.models.template import Template
from app.models.user import USER_ROLES, User

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


def normalize_scope(value: str | None) -> str:
    """Comparison key for a free-text organization / department name."""
    return (value or "").strip().lower()


def clean_scope(value: str | None) -> str | None:
    """Storage form of a scope value: stripped, empty -> None."""
    stripped = (value or "").strip()
    return stripped or None


def _sql_norm(column) -> ColumnElement:
    return func.lower(func.trim(column))


def _same(a: str | None, b: str | None) -> bool:
    key = normalize_scope(a)
    return bool(key) and key == normalize_scope(b)


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


def _scope_org_unset(template: Template) -> bool:
    return normalize_scope(template.scope_organization) == ""


def _department_scope_matches(user: User, template: Template) -> bool:
    return _same(user.department, template.scope_department) and (
        _scope_org_unset(template)
        or _same(user.organization, template.scope_organization)
    )


def is_scope_manager(user: User, template: Template) -> bool:
    """org_admin / department_admin who administers the template's scope."""
    if template.visibility not in SCOPED_VISIBILITIES:
        return False
    if user.role == "org_admin":
        return _same(user.organization, template.scope_organization)
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
        return _same(
            user.organization, template.scope_organization
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
    user_org = normalize_scope(user.organization)
    user_dept = normalize_scope(user.department)
    role_ok = _sql_role_allowed(role)

    conditions: list[ColumnElement] = [
        Template.uploaded_by == user.id,
        and_(Template.visibility == "public", role_ok),
    ]

    org_match = (
        _sql_norm(Template.scope_organization) == user_org if user_org else false()
    )
    scope_org_unset = or_(
        Template.scope_organization.is_(None),
        func.trim(Template.scope_organization) == "",
    )

    if user_org:
        org_template = and_(Template.visibility == "organization", org_match)
        if role == "org_admin":
            # Scope manager: every org and department template of their org.
            conditions.append(org_template)
            conditions.append(and_(Template.visibility == "department", org_match))
        else:
            conditions.append(and_(org_template, role_ok))

    if user_dept:
        dept_scope = and_(
            Template.visibility == "department",
            _sql_norm(Template.scope_department) == user_dept,
            or_(scope_org_unset, org_match),
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
    scope_organization: str | None
    scope_department: str | None
    allowed_roles: str | None  # JSON text, as stored


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


def _require_match(provided: str | None, own: str, what: str) -> None:
    if clean_scope(provided) is not None and normalize_scope(provided) != normalize_scope(
        own
    ):
        raise PublishRuleError(403, f"You can only publish to your own {what} ({own})")


def resolve_publish_access(
    user: User,
    visibility: str,
    scope_organization: str | None,
    scope_department: str | None,
    allowed_roles: Iterable[str] | None,
) -> ResolvedAccess:
    """
    Apply the publish rules for `user` and return the values to store.
    Raises PublishRuleError (403 / 422) with a user-facing message.

    - organization / department visibility: super_admin, org_admin,
      department_admin only (department_admin: department visibility only).
    - org_admin: scope_organization is forced to their own organization
      (a different explicit value -> 403).
    - department_admin: scope forced to their own department + organization.
    - super_admin: must name scope_organization (and scope_department for
      department visibility).
    - private / public / group: scope cleared; allowed_roles kept for public
      only (it has no meaning for private / group).
    """
    roles = validate_allowed_roles(allowed_roles)

    if visibility not in SCOPED_VISIBILITIES:
        return ResolvedAccess(
            visibility=visibility,
            scope_organization=None,
            scope_department=None,
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

    org = clean_scope(scope_organization)
    dept = clean_scope(scope_department)

    if user.role == "org_admin":
        own_org = clean_scope(user.organization)
        if own_org is None:
            raise PublishRuleError(
                422, "Your profile has no organization; set it before publishing"
            )
        _require_match(org, own_org, "organization")
        org = own_org
    elif user.role == "department_admin":
        own_dept = clean_scope(user.department)
        if own_dept is None:
            raise PublishRuleError(
                422, "Your profile has no department; set it before publishing"
            )
        own_org = clean_scope(user.organization)
        _require_match(dept, own_dept, "department")
        if own_org is not None:
            _require_match(org, own_org, "organization")
        dept = own_dept
        org = own_org
    elif org is None:  # super_admin
        raise PublishRuleError(
            422, "scope_organization is required for organization/department visibility"
        )

    if visibility == "department":
        if dept is None:
            raise PublishRuleError(
                422, "scope_department is required for department visibility"
            )
    else:
        dept = None

    return ResolvedAccess(
        visibility=visibility,
        scope_organization=org,
        scope_department=dept,
        allowed_roles=serialize_allowed_roles(roles),
    )
