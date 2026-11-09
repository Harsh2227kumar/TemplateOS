"""
Organization / department directory helpers.

- Name hygiene: `clean_name` (trim + collapse whitespace) and
  case-insensitive lookups, matching the unique indexes on lower(name).
- Membership / scope writers: `set_user_membership` and `set_template_scope`
  are the ONLY places that write users.organization_id / department_id and
  templates.scope_organization_id / scope_department_id. They also write the
  legacy free-text columns (users.organization / department,
  templates.scope_organization / scope_department) as copies of the linked
  names, so older code and a migration rollback keep working. Renames
  propagate to those copies (`rename_organization`, `rename_department`).
- Usage counts for the "409 when in use" delete rule.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.models.organization import Department, Institute, Organization
from app.models.template import Template
from app.models.user import User

NAME_MAX_LENGTH = 255


class DirectoryError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def clean_name(value: str | None) -> str | None:
    """Storage form of a name: trimmed, internal whitespace collapsed; blank -> None."""
    if value is None:
        return None
    collapsed = " ".join(value.split())
    return collapsed or None


def require_name(value: str | None, what: str) -> str:
    name = clean_name(value)
    if name is None:
        raise DirectoryError(422, f"{what} name is required")
    if len(name) > NAME_MAX_LENGTH:
        raise DirectoryError(
            422, f"{what} name must be {NAME_MAX_LENGTH} characters or fewer"
        )
    return name


# ── lookups ──────────────────────────────────────────────────────────


def get_organization(db: Session, organization_id: int) -> Organization | None:
    return db.get(Organization, organization_id)


def get_department(db: Session, department_id: int) -> Department | None:
    return db.get(Department, department_id)


def find_organization_by_name(db: Session, name: str | None) -> Organization | None:
    cleaned = clean_name(name)
    if cleaned is None:
        return None
    return db.scalar(
        select(Organization).where(func.lower(Organization.name) == cleaned.lower())
    )


def find_department_by_name(
    db: Session,
    organization_id: int,
    name: str | None,
    institute_id: int | None = None,
) -> Department | None:
    """Department by name inside an organization (and institute, when given).
    Names are unique per institute, so without an institute the first match
    (lowest id) is returned."""
    cleaned = clean_name(name)
    if cleaned is None:
        return None
    query = select(Department).where(
        Department.organization_id == organization_id,
        func.lower(Department.name) == cleaned.lower(),
    )
    if institute_id is not None:
        query = query.where(Department.institute_id == institute_id)
    return db.scalars(query.order_by(Department.id)).first()


def get_institute(db: Session, institute_id: int) -> Institute | None:
    return db.get(Institute, institute_id)


def find_institute_by_name(
    db: Session, organization_id: int, name: str | None
) -> Institute | None:
    cleaned = clean_name(name)
    if cleaned is None:
        return None
    return db.scalar(
        select(Institute).where(
            Institute.organization_id == organization_id,
            func.lower(Institute.name) == cleaned.lower(),
        )
    )


def find_by_code(db: Session, model, code: str | None, **parent):
    """Row of `model` with this code (case-insensitive) under the given parent ids."""
    if not code or not str(code).strip():
        return None
    query = select(model).where(func.upper(model.code) == str(code).strip().upper())
    for column, value in parent.items():
        query = query.where(getattr(model, column) == value)
    return db.scalars(query.order_by(model.id)).first()


def clean_code(value: str | None) -> str | None:
    """Codes are stored upper-case without spaces; blank -> None."""
    if value is None:
        return None
    code = "".join(str(value).split()).upper()
    if not code:
        return None
    if len(code) > 32 or not all(ch.isalnum() or ch == "-" for ch in code):
        raise DirectoryError(422, "Codes may contain only letters, digits and '-' (max 32)")
    return code


def require_organization(db: Session, organization_id: int) -> Organization:
    organization = get_organization(db, organization_id)
    if organization is None:
        raise DirectoryError(422, f"Organization {organization_id} does not exist")
    return organization


def require_department(db: Session, department_id: int) -> Department:
    department = get_department(db, department_id)
    if department is None:
        raise DirectoryError(422, f"Department {department_id} does not exist")
    return department


# ── writers (keep the legacy name columns in sync) ───────────────────


def set_user_membership(
    user: User,
    organization: Organization | None,
    department: Department | None,
    institute: Institute | None = None,
) -> None:
    """
    Place a user. A department implies its institute; an institute must be
    inside the organization; a department must be inside the institute.
    """
    if department is not None and (
        organization is None or department.organization_id != organization.id
    ):
        raise DirectoryError(
            422, "The department must belong to the user's organization"
        )
    if department is not None and department.institute_id is not None:
        if institute is not None and institute.id != department.institute_id:
            raise DirectoryError(
                422, "The department must belong to the user's institute"
            )
        institute = department.institute
    if institute is not None and (
        organization is None or institute.organization_id != organization.id
    ):
        raise DirectoryError(
            422, "The institute must belong to the user's organization"
        )
    user.organization_id = organization.id if organization else None
    user.institute_id = institute.id if institute else None
    user.department_id = department.id if department else None
    user.organization_ref = organization
    user.institute_ref = institute
    user.department_ref = department
    user.organization = organization.name if organization else None
    user.department = department.name if department else None


def set_template_scope(
    template: Template,
    organization: Organization | None,
    department: Department | None,
    institute: Institute | None = None,
) -> None:
    if department is not None and (
        organization is None or department.organization_id != organization.id
    ):
        raise DirectoryError(
            422, "The department must belong to the template's organization"
        )
    if department is not None and department.institute_id is not None:
        institute = department.institute
    if institute is not None and (
        organization is None or institute.organization_id != organization.id
    ):
        raise DirectoryError(
            422, "The institute must belong to the template's organization"
        )
    template.scope_organization_id = organization.id if organization else None
    template.scope_institute_id = institute.id if institute else None
    template.scope_department_id = department.id if department else None
    template.scope_organization_ref = organization
    template.scope_institute_ref = institute
    template.scope_department_ref = department
    template.scope_organization = organization.name if organization else None
    template.scope_department = department.name if department else None


# ── create / rename ──────────────────────────────────────────────────


def create_organization(db: Session, name: str | None) -> Organization:
    cleaned = require_name(name, "Organization")
    if find_organization_by_name(db, cleaned) is not None:
        raise DirectoryError(409, f"An organization named '{cleaned}' already exists")
    organization = Organization(name=cleaned)
    db.add(organization)
    db.flush()
    return organization


def rename_organization(db: Session, organization: Organization, name: str | None) -> None:
    cleaned = require_name(name, "Organization")
    existing = find_organization_by_name(db, cleaned)
    if existing is not None and existing.id != organization.id:
        raise DirectoryError(409, f"An organization named '{cleaned}' already exists")
    organization.name = cleaned
    db.execute(
        update(User)
        .where(User.organization_id == organization.id)
        .values(organization=cleaned)
        .execution_options(synchronize_session=False)
    )
    db.execute(
        update(Template)
        .where(Template.scope_organization_id == organization.id)
        .values(scope_organization=cleaned)
        .execution_options(synchronize_session=False)
    )


def create_institute(
    db: Session, organization: Organization, name: str | None, code: str | None = None
) -> Institute:
    cleaned = require_name(name, "Institute")
    if find_institute_by_name(db, organization.id, cleaned) is not None:
        raise DirectoryError(
            409, f"An institute named '{cleaned}' already exists in {organization.name}"
        )
    code = clean_code(code)
    if code and find_by_code(db, Institute, code, organization_id=organization.id):
        raise DirectoryError(409, f"An institute with code '{code}' already exists")
    institute = Institute(organization_id=organization.id, name=cleaned, code=code)
    db.add(institute)
    db.flush()
    return institute


def rename_institute(db: Session, institute: Institute, name: str | None) -> None:
    cleaned = require_name(name, "Institute")
    existing = find_institute_by_name(db, institute.organization_id, cleaned)
    if existing is not None and existing.id != institute.id:
        raise DirectoryError(409, f"An institute named '{cleaned}' already exists")
    institute.name = cleaned


def default_institute(db: Session, organization: Organization) -> Institute:
    """The organization's only institute, created on demand for callers that
    create a department without naming an institute (older clients)."""
    institutes = db.scalars(
        select(Institute)
        .where(Institute.organization_id == organization.id)
        .order_by(Institute.id)
    ).all()
    if len(institutes) == 1:
        return institutes[0]
    if not institutes:
        return create_institute(db, organization, organization.name, "MAIN")
    raise DirectoryError(
        422, "institute_id is required: this organization has several institutes"
    )


def create_department(
    db: Session,
    organization: Organization,
    name: str | None,
    institute: Institute | None = None,
    code: str | None = None,
) -> Department:
    cleaned = require_name(name, "Department")
    if institute is None:
        institute = default_institute(db, organization)
    if institute.organization_id != organization.id:
        raise DirectoryError(422, "The institute must belong to the organization")
    duplicate = find_department_by_name(db, organization.id, cleaned, institute.id)
    if duplicate is None:
        # Departments created before institutes existed have no institute yet.
        legacy = find_department_by_name(db, organization.id, cleaned)
        if legacy is not None and legacy.institute_id is None:
            duplicate = legacy
    if duplicate is not None:
        raise DirectoryError(
            409,
            f"A department named '{cleaned}' already exists in {institute.name}",
        )
    code = clean_code(code)
    if code and find_by_code(db, Department, code, institute_id=institute.id):
        raise DirectoryError(
            409, f"A department with code '{code}' already exists in {institute.name}"
        )
    department = Department(
        organization_id=organization.id,
        institute_id=institute.id,
        name=cleaned,
        code=code,
    )
    db.add(department)
    db.flush()
    return department


def rename_department(db: Session, department: Department, name: str | None) -> None:
    cleaned = require_name(name, "Department")
    existing = find_department_by_name(
        db, department.organization_id, cleaned, department.institute_id
    )
    if existing is not None and existing.id != department.id:
        raise DirectoryError(
            409, f"A department named '{cleaned}' already exists in this institute"
        )
    department.name = cleaned
    db.execute(
        update(User)
        .where(User.department_id == department.id)
        .values(department=cleaned)
        .execution_options(synchronize_session=False)
    )
    db.execute(
        update(Template)
        .where(Template.scope_department_id == department.id)
        .values(scope_department=cleaned)
        .execution_options(synchronize_session=False)
    )


# ── usage (delete guard) ─────────────────────────────────────────────


def organization_usage(db: Session, organization_id: int) -> tuple[int, int]:
    """(users, templates) linked to the organization or any of its departments."""
    dept_ids = select(Department.id).where(Department.organization_id == organization_id)
    users = db.scalar(
        select(func.count(User.id)).where(
            or_(
                User.organization_id == organization_id,
                User.department_id.in_(dept_ids),
            )
        )
    )
    templates = db.scalar(
        select(func.count(Template.id)).where(
            or_(
                Template.scope_organization_id == organization_id,
                Template.scope_department_id.in_(dept_ids),
            )
        )
    )
    return users or 0, templates or 0


def institute_usage(db: Session, institute_id: int) -> tuple[int, int]:
    """(users, templates) linked to the institute or any of its departments."""
    dept_ids = select(Department.id).where(Department.institute_id == institute_id)
    users = db.scalar(
        select(func.count(User.id)).where(
            or_(User.institute_id == institute_id, User.department_id.in_(dept_ids))
        )
    )
    templates = db.scalar(
        select(func.count(Template.id)).where(
            or_(
                Template.scope_institute_id == institute_id,
                Template.scope_department_id.in_(dept_ids),
            )
        )
    )
    return users or 0, templates or 0


def department_usage(db: Session, department_id: int) -> tuple[int, int]:
    users = db.scalar(
        select(func.count(User.id)).where(User.department_id == department_id)
    )
    templates = db.scalar(
        select(func.count(Template.id)).where(
            Template.scope_department_id == department_id
        )
    )
    return users or 0, templates or 0


def in_use_detail(what: str, users: int, templates: int) -> str:
    parts = []
    if users:
        parts.append(f"{users} user{'s' if users != 1 else ''}")
    if templates:
        parts.append(f"{templates} template{'s' if templates != 1 else ''}")
    return (
        f"This {what} is still in use by {' and '.join(parts)}. "
        "Reassign them before deleting it."
    )
