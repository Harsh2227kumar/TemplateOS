"""
Who may read which audit rows.

- super_admin: every row
- org_admin (with an organization): rows of their organization
- institute_admin (with an institute): rows of their institute
- department_admin (with a department): rows of their department
- everyone else, or an admin without that membership: nothing

audit_scope_filter() applies the rule in SQL, so pagination totals are
right; row_visible_to() is its Python twin. The two must agree
(tests/test_audit_scope_parity.py).
"""

from sqlalchemy import ColumnElement, false

from app.models.audit_log import AuditLog
from app.models.user import User
from app.services import scopes


def can_view_audit(user: User) -> bool:
    return scopes.scope_of(user) is not None


def audit_scope_filter(user: User) -> ColumnElement[bool] | None:
    """WHERE clause for the rows `user` may read; None means every row."""
    scope = scopes.scope_of(user)
    if scope is None:
        return false()
    if scope.level == "platform":
        return None
    column = {
        "organization": AuditLog.organization_id,
        "institute": AuditLog.institute_id,
        "department": AuditLog.department_id,
    }[scope.level]
    return column == scope.id


def row_visible_to(user: User, row: AuditLog) -> bool:
    """Python twin of audit_scope_filter (parity-tested)."""
    return scopes.contains(
        scopes.scope_of(user), row.organization_id, row.institute_id, row.department_id
    )
