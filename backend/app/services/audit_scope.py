"""
Who may read which audit rows (V1.7 Phase 3).

- super_admin: every row
- org_admin (with an organization): rows of their organization
- department_admin (with a department): rows of their department
- everyone else, or an admin without that membership: nothing

audit_scope_filter() applies the rule in SQL, so pagination totals are
right; row_visible_to() is its Python twin. The two must agree
(tests/test_audit_scope_parity.py).
"""

from sqlalchemy import ColumnElement, false

from app.models.audit_log import AuditLog
from app.models.user import User


def can_view_audit(user: User) -> bool:
    if user.role == "super_admin":
        return True
    if user.role == "org_admin":
        return user.organization_id is not None
    if user.role == "department_admin":
        return user.department_id is not None
    return False


def audit_scope_filter(user: User) -> ColumnElement[bool] | None:
    """WHERE clause for the rows `user` may read; None means every row."""
    if user.role == "super_admin":
        return None
    if user.role == "org_admin" and user.organization_id is not None:
        return AuditLog.organization_id == user.organization_id
    if user.role == "department_admin" and user.department_id is not None:
        return AuditLog.department_id == user.department_id
    return false()


def row_visible_to(user: User, row: AuditLog) -> bool:
    """Python twin of audit_scope_filter (parity-tested)."""
    if user.role == "super_admin":
        return True
    if user.role == "org_admin" and user.organization_id is not None:
        return row.organization_id == user.organization_id
    if user.role == "department_admin" and user.department_id is not None:
        return row.department_id == user.department_id
    return False
