"""
Administration API: users, the organization -> institute -> department
directory, and approver assignments. Mounted at /api/v1/admin.

Users (rules: app/services/user_admin.py)
  GET    /admin/users                 any admin, inside their scope
  PATCH  /admin/users/{id}            role, organization_id, institute_id,
                                      department_id, member_type, is_active
                                      (deactivation also ends the user's sessions)

Organizations
  GET    /admin/organizations         any signed-in user (pickers need it)
  POST   /admin/organizations         super_admin
  PATCH  /admin/organizations/{id}    super_admin (name, code, is_active)
  DELETE /admin/organizations/{id}    super_admin; 409 while anything uses it

Institutes
  GET    /admin/institutes?organization_id=
                                      super_admin: all; others: their organization's
                                      (institute / department admins: their own)
  POST   /admin/institutes            super_admin anywhere, org_admin in their org
  PATCH  /admin/institutes/{id}       same (name, code, is_active)
  DELETE /admin/institutes/{id}       same; 409 while any department, user or
                                      template uses it

Departments
  GET    /admin/departments?organization_id=&institute_id=
  POST   /admin/departments           super_admin anywhere, org_admin in their
                                      organization, institute_admin in their institute
  PATCH  /admin/departments/{id}      same (name, code, is_active)
  DELETE /admin/departments/{id}      same; 409 while any user or template uses it

Approver assignments (rules: app/services/approver_assignments.py)
  GET    /admin/approvers             admins: inside their scope
  POST   /admin/approvers             admins: inside their scope; 409 "Assign
                                      approvers in EkLink" while EkLink sync is on
  POST   /admin/approvers/{id}/end    end an assignment (never deleted); 409 for
                                      rows mirrored from EkLink (source 'eklink')

EkLink ownership (SYNC_CONTRACT.md section 7): directory rows with a code are
mirrored from EkLink, so renaming, recoding, toggling, deleting them or
creating rows under them is 409 "Managed in EkLink" (local rows without a
code stay editable; codes are only assigned by EkLink). EkLink-linked users:
see app/services/user_admin.py. Responses carry `managed_by_eklink`.

Unsafe cookie requests need the CSRF header (app/core/csrf.py middleware).
"""

import logging

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import func, or_, select, update

from app.api.deps import CurrentUser, DbSession
from app.core.clock import utc_now_naive
from app.core.config import settings
from app.models.approver_assignment import APPROVER_TITLES, ApproverAssignment
from app.models.organization import Department, Institute, Organization
from app.models.refresh_token import RefreshToken
from app.models.user import MEMBER_TYPES, STORED_ROLES, User
from app.schemas.approver import (
    ApproverAssignmentCreate,
    ApproverAssignmentList,
    ApproverAssignmentRead,
)
from app.schemas.organization import (
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    InstituteCreate,
    InstituteRead,
    InstituteUpdate,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
)
from app.schemas.user import AdminUserList, AdminUserRead, AdminUserUpdate
from app.services import approver_assignments as approvers
from app.services import audit_service, scopes
from app.services.org_directory import (
    DirectoryError,
    clean_code,
    create_department,
    create_institute,
    create_organization,
    department_usage,
    find_by_code,
    in_use_detail,
    institute_usage,
    organization_usage,
    rename_department,
    rename_institute,
    rename_organization,
)
from app.services.user_admin import (
    UserAdminError,
    apply_user_update,
    require_user_admin,
    user_scope_filter,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _http(exc: UserAdminError | DirectoryError | approvers.AssignmentError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ── users ────────────────────────────────────────────────────────────


@router.get("/users", response_model=AdminUserList)
def list_users(
    current_user: CurrentUser,
    db: DbSession,
    search: str | None = Query(None, max_length=100, description="Name, email or login ID"),
    role: str | None = Query(None),
    organization_id: int | None = Query(None),
    institute_id: int | None = Query(None),
    department_id: int | None = Query(None),
    member_type: str | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> AdminUserList:
    try:
        require_user_admin(current_user)
    except UserAdminError as exc:
        raise _http(exc) from None
    if role is not None and role not in STORED_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role. Allowed: {', '.join(STORED_ROLES)}",
        )
    # One or more member types, comma-separated (e.g. "faculty,staff" for approver pickers).
    member_types = (
        [part.strip() for part in member_type.split(",") if part.strip()] if member_type else []
    )
    if any(value not in MEMBER_TYPES for value in member_types):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid member type. Allowed: {', '.join(MEMBER_TYPES)}",
        )

    query = select(User)
    scope = user_scope_filter(current_user)
    if scope is not None:
        query = query.where(scope)
    if search and search.strip():
        pattern = f"%{_escape_like(search.strip())}%"
        query = query.where(
            or_(
                User.full_name.ilike(pattern, escape="\\"),
                User.email.ilike(pattern, escape="\\"),
                User.login_id.ilike(pattern, escape="\\"),
            )
        )
    if role is not None:
        query = query.where(User.role == role)
    if organization_id is not None:
        query = query.where(User.organization_id == organization_id)
    if institute_id is not None:
        query = query.where(User.institute_id == institute_id)
    if department_id is not None:
        query = query.where(User.department_id == department_id)
    if member_types:
        query = query.where(User.member_type.in_(member_types))
    if is_active is not None:
        query = query.where(User.is_active.is_(is_active))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    users = db.scalars(
        query.order_by(func.lower(User.full_name), User.id)
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return AdminUserList(
        users=[AdminUserRead.model_validate(user) for user in users],
        total=total,
        page=page,
        limit=limit,
    )


# Only ids, the role and flags are recorded with old -> new values (no personal data).
_AUDITED_USER_KEYS = (
    "role",
    "organization_id",
    "institute_id",
    "department_id",
    "member_type",
    "is_active",
)


def _end_sessions(db, user_id: int) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utc_now_naive())
    )


@router.patch("/users/{user_id}", response_model=AdminUserRead)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
) -> AdminUserRead:
    try:
        require_user_admin(current_user)
    except UserAdminError as exc:
        raise _http(exc) from None
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    changes = payload.model_dump(exclude_unset=True)
    before = {key: getattr(target, key) for key in _AUDITED_USER_KEYS}
    try:
        apply_user_update(db, current_user, target, changes)
    except (UserAdminError, DirectoryError) as exc:
        db.rollback()
        raise _http(exc) from None
    if before["is_active"] and not target.is_active:
        _end_sessions(db, target.id)
    db.commit()
    db.refresh(target)
    diff = {
        key: [before[key], getattr(target, key)]
        for key in _AUDITED_USER_KEYS
        if before[key] != getattr(target, key)
    }
    action = "admin.user_update"
    if "is_active" in diff:
        action = "admin.user_reactivate" if target.is_active else "admin.user_deactivate"
    audit_service.record_and_commit(
        db,
        request,
        actor=current_user,
        action=action,
        entity_type="user",
        entity_id=target.id,
        summary=f"Updated user {target.email}" + (f": {', '.join(diff)}" if diff else ""),
        details={"changed": diff, "fields": sorted(changes)},
        organization_id=target.organization_id,
        department_id=target.department_id,
        institute_id_hint=target.institute_id,
    )
    logger.info(
        f"User {current_user.id} updated user {target.id}: role={target.role}, "
        f"org={target.organization_id}, inst={target.institute_id}, "
        f"dept={target.department_id}, active={target.is_active}"
    )
    return AdminUserRead.model_validate(target)


# ── organizations ────────────────────────────────────────────────────


def _require_super_admin(user: User, action: str) -> None:
    if user.role != "super_admin":
        raise HTTPException(
            status_code=403, detail=f"Only a super admin can {action} organizations"
        )


def _organization_read(db, organization: Organization) -> OrganizationRead:
    def count(model, column) -> int:
        return db.scalar(select(func.count(model.id)).where(column == organization.id)) or 0

    return OrganizationRead(
        id=organization.id,
        name=organization.name,
        code=organization.code,
        is_active=organization.is_active,
        is_demo=organization.is_demo,
        managed_by_eklink=organization.managed_by_eklink,
        created_at=organization.created_at,
        institute_count=count(Institute, Institute.organization_id),
        department_count=count(Department, Department.organization_id),
        user_count=count(User, User.organization_id),
    )


@router.get("/organizations", response_model=list[OrganizationRead])
def list_organizations(current_user: CurrentUser, db: DbSession) -> list[OrganizationRead]:
    def counts(model, column):
        return (
            select(column.label("key"), func.count(model.id).label("n"))
            .where(column.is_not(None))
            .group_by(column)
            .subquery()
        )

    inst_counts = counts(Institute, Institute.organization_id)
    dept_counts = counts(Department, Department.organization_id)
    user_counts = counts(User, User.organization_id)
    rows = db.execute(
        select(Organization, inst_counts.c.n, dept_counts.c.n, user_counts.c.n)
        .outerjoin(inst_counts, inst_counts.c.key == Organization.id)
        .outerjoin(dept_counts, dept_counts.c.key == Organization.id)
        .outerjoin(user_counts, user_counts.c.key == Organization.id)
        .order_by(func.lower(Organization.name))
    ).all()
    return [
        OrganizationRead(
            id=org.id,
            name=org.name,
            code=org.code,
            is_active=org.is_active,
            is_demo=org.is_demo,
            managed_by_eklink=org.managed_by_eklink,
            created_at=org.created_at,
            institute_count=inst_n or 0,
            department_count=dept_n or 0,
            user_count=user_n or 0,
        )
        for org, inst_n, dept_n, user_n in rows
    ]


MANAGED_IN_EKLINK = "Managed in EkLink"


def _reject_managed(row, what: str) -> None:
    """Directory rows with a code are mirrored from EkLink (read-only here)."""
    if row is not None and row.code is not None:
        raise HTTPException(
            status_code=409,
            detail=f"{MANAGED_IN_EKLINK}: change this {what} in the EkLink Admin Console",
        )


def _reject_code(code: str | None) -> None:
    if code is not None and str(code).strip():
        raise HTTPException(
            status_code=409,
            detail=f"{MANAGED_IN_EKLINK}: codes are assigned in EkLink",
        )


def _set_code(db, row, model, code: str | None, **parent) -> None:
    cleaned = clean_code(code)
    if cleaned is not None:
        other = find_by_code(db, model, cleaned, **parent)
        if other is not None and other.id != row.id:
            raise DirectoryError(409, f"The code '{cleaned}' is already in use")
    row.code = cleaned


@router.post(
    "/organizations",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_organization_endpoint(
    payload: OrganizationCreate, current_user: CurrentUser, db: DbSession, request: Request
) -> OrganizationRead:
    _require_super_admin(current_user, "create")
    _reject_code(payload.code)
    try:
        organization = create_organization(db, payload.name)
        if payload.code is not None:
            _set_code(db, organization, Organization, payload.code)
    except DirectoryError as exc:
        db.rollback()
        raise _http(exc) from None
    db.commit()
    db.refresh(organization)
    audit_service.record_and_commit(
        db, request, actor=current_user, action="admin.organization_create", entity_type="organization",
        entity_id=organization.id, summary=f"Created organization '{organization.name}'",
        organization_id=organization.id,
    )
    return _organization_read(db, organization)


@router.patch("/organizations/{organization_id}", response_model=OrganizationRead)
def update_organization_endpoint(
    organization_id: int,
    payload: OrganizationUpdate,
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
) -> OrganizationRead:
    _require_super_admin(current_user, "update")
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    _reject_managed(organization, "organization")
    changes = payload.model_dump(exclude_unset=True)
    _reject_code(changes.get("code"))
    before = {"name": organization.name, "code": organization.code, "is_active": organization.is_active}
    try:
        if changes.get("name") is not None:
            rename_organization(db, organization, changes["name"])
        if "code" in changes:
            _set_code(db, organization, Organization, changes["code"])
        if changes.get("is_active") is not None:
            organization.is_active = changes["is_active"]
    except DirectoryError as exc:
        db.rollback()
        raise _http(exc) from None
    db.commit()
    db.refresh(organization)
    after = {"name": organization.name, "code": organization.code, "is_active": organization.is_active}
    audit_service.record_and_commit(
        db, request, actor=current_user, action="admin.organization_update", entity_type="organization",
        entity_id=organization.id, summary=f"Updated organization '{organization.name}'",
        details={k: [before[k], after[k]] for k in after if before[k] != after[k]},
        organization_id=organization.id,
    )
    return _organization_read(db, organization)


@router.delete(
    "/organizations/{organization_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_organization_endpoint(
    organization_id: int, current_user: CurrentUser, db: DbSession, request: Request
) -> Response:
    _require_super_admin(current_user, "delete")
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    _reject_managed(organization, "organization")
    users, templates = organization_usage(db, organization_id)
    if users or templates:
        raise HTTPException(
            status_code=409, detail=in_use_detail("organization", users, templates)
        )
    name = organization.name
    db.delete(organization)  # its (unused) institutes and departments cascade
    db.commit()
    audit_service.record_and_commit(
        db, request, actor=current_user, action="admin.organization_delete", entity_type="organization",
        entity_id=organization_id, summary=f"Deleted organization '{name}'",
        actor_scope=False,
    )
    logger.info(f"Super admin {current_user.id} deleted organization {organization_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── institutes ───────────────────────────────────────────────────────


def _require_institute_manager(user: User, organization_id: int | None) -> None:
    """super_admin anywhere; org_admin only inside their own organization."""
    if user.role == "super_admin":
        return
    if user.role == "org_admin":
        if user.organization_id is not None and user.organization_id == organization_id:
            return
        raise HTTPException(
            status_code=403, detail="You can only manage institutes of your own organization"
        )
    raise HTTPException(
        status_code=403,
        detail="Only super admins and organization admins can manage institutes",
    )


def _institute_read(db, institute: Institute) -> InstituteRead:
    departments = db.scalar(
        select(func.count(Department.id)).where(Department.institute_id == institute.id)
    )
    users = db.scalar(select(func.count(User.id)).where(User.institute_id == institute.id))
    return InstituteRead(
        id=institute.id,
        organization_id=institute.organization_id,
        name=institute.name,
        code=institute.code,
        is_active=institute.is_active,
        is_demo=institute.is_demo,
        managed_by_eklink=institute.managed_by_eklink,
        created_at=institute.created_at,
        department_count=departments or 0,
        user_count=users or 0,
    )


@router.get("/institutes", response_model=list[InstituteRead])
def list_institutes(
    current_user: CurrentUser,
    db: DbSession,
    organization_id: int | None = Query(None),
) -> list[InstituteRead]:
    query = select(Institute)
    if current_user.role == "super_admin":
        if organization_id is not None:
            query = query.where(Institute.organization_id == organization_id)
    else:
        own = current_user.organization_id
        if own is None:
            return []
        if organization_id is not None and organization_id != own:
            raise HTTPException(
                status_code=403, detail="You can only list institutes of your own organization"
            )
        query = query.where(Institute.organization_id == own)
        if current_user.role in ("institute_admin", "department_admin"):
            query = query.where(Institute.id == current_user.institute_id)
    institutes = db.scalars(
        query.order_by(Institute.organization_id, func.lower(Institute.name))
    ).all()
    return [_institute_read(db, institute) for institute in institutes]


@router.post("/institutes", response_model=InstituteRead, status_code=status.HTTP_201_CREATED)
def create_institute_endpoint(
    payload: InstituteCreate, current_user: CurrentUser, db: DbSession, request: Request
) -> InstituteRead:
    organization_id = payload.organization_id
    if organization_id is None and current_user.role == "org_admin":
        organization_id = current_user.organization_id
    if organization_id is None and current_user.role == "super_admin":
        raise HTTPException(status_code=422, detail="organization_id is required")
    _require_institute_manager(current_user, organization_id)
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=422, detail=f"Organization {organization_id} does not exist")
    _reject_managed(organization, "organization's institutes")
    _reject_code(payload.code)
    try:
        institute = create_institute(db, organization, payload.name, payload.code)
    except DirectoryError as exc:
        db.rollback()
        raise _http(exc) from None
    db.commit()
    db.refresh(institute)
    audit_service.record_and_commit(
        db, request, actor=current_user, action="admin.institute_create", entity_type="institute",
        entity_id=institute.id, summary=f"Created institute '{institute.name}' in '{organization.name}'",
        organization_id=organization.id, institute_id_hint=institute.id,
    )
    return _institute_read(db, institute)


def _get_institute_or_404(db, institute_id: int) -> Institute:
    institute = db.get(Institute, institute_id)
    if institute is None:
        raise HTTPException(status_code=404, detail="Institute not found")
    return institute


@router.patch("/institutes/{institute_id}", response_model=InstituteRead)
def update_institute_endpoint(
    institute_id: int,
    payload: InstituteUpdate,
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
) -> InstituteRead:
    institute = _get_institute_or_404(db, institute_id)
    _require_institute_manager(current_user, institute.organization_id)
    _reject_managed(institute, "institute")
    changes = payload.model_dump(exclude_unset=True)
    _reject_code(changes.get("code"))
    before = {"name": institute.name, "code": institute.code, "is_active": institute.is_active}
    try:
        if changes.get("name") is not None:
            rename_institute(db, institute, changes["name"])
        if "code" in changes:
            _set_code(db, institute, Institute, changes["code"], organization_id=institute.organization_id)
        if changes.get("is_active") is not None:
            institute.is_active = changes["is_active"]
    except DirectoryError as exc:
        db.rollback()
        raise _http(exc) from None
    db.commit()
    db.refresh(institute)
    after = {"name": institute.name, "code": institute.code, "is_active": institute.is_active}
    audit_service.record_and_commit(
        db, request, actor=current_user, action="admin.institute_update", entity_type="institute",
        entity_id=institute.id, summary=f"Updated institute '{institute.name}'",
        details={k: [before[k], after[k]] for k in after if before[k] != after[k]},
        organization_id=institute.organization_id, institute_id_hint=institute.id,
    )
    return _institute_read(db, institute)


@router.delete("/institutes/{institute_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_institute_endpoint(
    institute_id: int, current_user: CurrentUser, db: DbSession, request: Request
) -> Response:
    institute = _get_institute_or_404(db, institute_id)
    _require_institute_manager(current_user, institute.organization_id)
    _reject_managed(institute, "institute")
    departments = db.scalar(
        select(func.count(Department.id)).where(Department.institute_id == institute_id)
    ) or 0
    users, templates = institute_usage(db, institute_id)
    if departments or users or templates:
        parts = in_use_detail("institute", users, templates) if (users or templates) else (
            f"This institute still has {departments} department"
            f"{'s' if departments != 1 else ''}. Remove or move them first."
        )
        raise HTTPException(status_code=409, detail=parts)
    name, organization_id = institute.name, institute.organization_id
    db.delete(institute)
    db.commit()
    audit_service.record_and_commit(
        db, request, actor=current_user, action="admin.institute_delete", entity_type="institute",
        entity_id=institute_id, summary=f"Deleted institute '{name}'",
        organization_id=organization_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── departments ──────────────────────────────────────────────────────


def _require_department_manager(user: User, department_scope: Department | Institute | None,
                                organization_id: int | None) -> None:
    """super_admin anywhere; org_admin inside their organization; institute_admin
    inside their institute."""
    if user.role == "super_admin":
        return
    if user.role == "org_admin":
        if user.organization_id is not None and user.organization_id == organization_id:
            return
        raise HTTPException(
            status_code=403,
            detail="You can only manage departments of your own organization",
        )
    if user.role == "institute_admin":
        institute_id = (
            department_scope.institute_id
            if isinstance(department_scope, Department)
            else (department_scope.id if department_scope is not None else None)
        )
        if user.institute_id is not None and user.institute_id == institute_id:
            return
        raise HTTPException(
            status_code=403, detail="You can only manage departments of your own institute"
        )
    raise HTTPException(
        status_code=403,
        detail="Only super admins, organization admins and institute admins can manage departments",
    )


def _department_read(db, department: Department) -> DepartmentRead:
    user_count = db.scalar(
        select(func.count(User.id)).where(User.department_id == department.id)
    )
    return DepartmentRead(
        id=department.id,
        organization_id=department.organization_id,
        institute_id=department.institute_id,
        name=department.name,
        code=department.code,
        is_active=department.is_active,
        is_demo=department.is_demo,
        managed_by_eklink=department.managed_by_eklink,
        created_at=department.created_at,
        user_count=user_count or 0,
    )


@router.get("/departments", response_model=list[DepartmentRead])
def list_departments(
    current_user: CurrentUser,
    db: DbSession,
    organization_id: int | None = Query(None),
    institute_id: int | None = Query(None),
) -> list[DepartmentRead]:
    query = select(Department)
    if current_user.role == "super_admin":
        if organization_id is not None:
            query = query.where(Department.organization_id == organization_id)
    else:
        own = current_user.organization_id
        if own is None:
            return []
        if organization_id is not None and organization_id != own:
            raise HTTPException(
                status_code=403,
                detail="You can only list departments of your own organization",
            )
        query = query.where(Department.organization_id == own)
        if current_user.role in ("institute_admin", "department_admin"):
            query = query.where(Department.institute_id == current_user.institute_id)
    if institute_id is not None:
        query = query.where(Department.institute_id == institute_id)

    user_counts = (
        select(User.department_id, func.count(User.id).label("n"))
        .where(User.department_id.is_not(None))
        .group_by(User.department_id)
        .subquery()
    )
    rows = db.execute(
        query.add_columns(user_counts.c.n)
        .outerjoin(user_counts, user_counts.c.department_id == Department.id)
        .order_by(Department.organization_id, func.lower(Department.name))
    ).all()
    return [
        DepartmentRead(
            id=dept.id,
            organization_id=dept.organization_id,
            institute_id=dept.institute_id,
            name=dept.name,
            code=dept.code,
            is_active=dept.is_active,
            is_demo=dept.is_demo,
            managed_by_eklink=dept.managed_by_eklink,
            created_at=dept.created_at,
            user_count=n or 0,
        )
        for dept, n in rows
    ]


@router.post(
    "/departments", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED
)
def create_department_endpoint(
    payload: DepartmentCreate, current_user: CurrentUser, db: DbSession, request: Request
) -> DepartmentRead:
    institute = None
    if payload.institute_id is not None:
        institute = db.get(Institute, payload.institute_id)
        if institute is None:
            raise HTTPException(status_code=422, detail=f"Institute {payload.institute_id} does not exist")
    elif current_user.role == "institute_admin" and current_user.institute_id is not None:
        institute = db.get(Institute, current_user.institute_id)

    organization_id = payload.organization_id
    if organization_id is None and institute is not None:
        organization_id = institute.organization_id
    if organization_id is None and current_user.role in ("org_admin", "institute_admin"):
        organization_id = current_user.organization_id
    if organization_id is None and current_user.role == "super_admin":
        raise HTTPException(status_code=422, detail="organization_id is required")
    _require_department_manager(current_user, institute, organization_id)
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(
            status_code=422, detail=f"Organization {organization_id} does not exist"
        )
    _reject_managed(institute, "institute's departments")
    if institute is None:
        _reject_managed(organization, "organization's departments")
    _reject_code(payload.code)
    try:
        department = create_department(db, organization, payload.name, institute, payload.code)
    except DirectoryError as exc:
        db.rollback()
        raise _http(exc) from None
    db.commit()
    db.refresh(department)
    audit_service.record_and_commit(
        db, request, actor=current_user, action="admin.department_create", entity_type="department",
        entity_id=department.id, summary=f"Created department '{department.name}' in '{organization.name}'",
        organization_id=department.organization_id, department_id=department.id,
    )
    return _department_read(db, department)


def _get_department_or_404(db, department_id: int) -> Department:
    department = db.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return department


@router.patch("/departments/{department_id}", response_model=DepartmentRead)
def update_department_endpoint(
    department_id: int,
    payload: DepartmentUpdate,
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
) -> DepartmentRead:
    department = _get_department_or_404(db, department_id)
    _require_department_manager(current_user, department, department.organization_id)
    _reject_managed(department, "department")
    changes = payload.model_dump(exclude_unset=True)
    _reject_code(changes.get("code"))
    before = {"name": department.name, "code": department.code, "is_active": department.is_active}
    try:
        if changes.get("name") is not None:
            rename_department(db, department, changes["name"])
        if "code" in changes:
            _set_code(db, department, Department, changes["code"], institute_id=department.institute_id)
        if changes.get("is_active") is not None:
            department.is_active = changes["is_active"]
    except DirectoryError as exc:
        db.rollback()
        raise _http(exc) from None
    db.commit()
    db.refresh(department)
    after = {"name": department.name, "code": department.code, "is_active": department.is_active}
    details = {k: [before[k], after[k]] for k in after if before[k] != after[k]}
    summary = (
        f"Renamed department '{before['name']}' to '{department.name}'"
        if before["name"] != department.name
        else f"Updated department '{department.name}'"
    )
    audit_service.record_and_commit(
        db, request, actor=current_user, action="admin.department_update", entity_type="department",
        entity_id=department.id, summary=summary, details=details,
        organization_id=department.organization_id, department_id=department.id,
    )
    return _department_read(db, department)


@router.delete("/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department_endpoint(
    department_id: int, current_user: CurrentUser, db: DbSession, request: Request
) -> Response:
    department = _get_department_or_404(db, department_id)
    _require_department_manager(current_user, department, department.organization_id)
    _reject_managed(department, "department")
    users, templates = department_usage(db, department_id)
    if users or templates:
        raise HTTPException(
            status_code=409, detail=in_use_detail("department", users, templates)
        )
    name, organization_id = department.name, department.organization_id
    db.delete(department)
    db.commit()
    audit_service.record_and_commit(
        db, request, actor=current_user, action="admin.department_delete", entity_type="department",
        entity_id=department_id, summary=f"Deleted department '{name}'",
        organization_id=organization_id, department_id=None,
    )
    logger.info(f"User {current_user.id} deleted department {department_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── approver assignments ─────────────────────────────────────────────


def _assignment_read(assignment: ApproverAssignment) -> ApproverAssignmentRead:
    scope_row = {
        "organization": assignment.organization,
        "institute": assignment.institute,
        "department": assignment.department,
    }.get(assignment.scope_level)
    user = assignment.user
    return ApproverAssignmentRead(
        id=assignment.id,
        user_id=assignment.user_id,
        user_name=user.full_name if user else None,
        user_email=user.email if user else None,
        user_login_id=user.login_id if user else None,
        title=assignment.title,
        scope_level=assignment.scope_level,
        organization_id=assignment.organization_id,
        institute_id=assignment.institute_id,
        department_id=assignment.department_id,
        scope_name=scope_row.name if scope_row is not None else None,
        scope_key=assignment.scope_key,
        valid_from=assignment.valid_from,
        valid_to=assignment.valid_to,
        is_current=approvers.is_current(assignment),
        created_at=assignment.created_at,
        source=assignment.source,
        eklink_id=assignment.eklink_id,
        managed_by_eklink=assignment.managed_by_eklink,
    )


@router.get("/approvers", response_model=ApproverAssignmentList)
def list_approvers(
    current_user: CurrentUser,
    db: DbSession,
    current_only: bool = Query(True),
    user_id: int | None = Query(None),
) -> ApproverAssignmentList:
    if not scopes.is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only administrators can manage approvers")
    query = select(ApproverAssignment)
    scope = approvers.assignment_scope_filter(current_user)
    if scope is not None:
        query = query.where(scope)
    if current_only:
        query = query.where(approvers.current_filter())
    if user_id is not None:
        query = query.where(ApproverAssignment.user_id == user_id)
    rows = db.scalars(
        query.order_by(ApproverAssignment.title, ApproverAssignment.valid_from.desc())
    ).all()
    return ApproverAssignmentList(
        assignments=[_assignment_read(row) for row in rows],
        total=len(rows),
        titles=list(APPROVER_TITLES),
        can_create=not settings.eklink_sync_enabled,
    )


@router.post(
    "/approvers", response_model=ApproverAssignmentRead, status_code=status.HTTP_201_CREATED
)
def create_approver(
    payload: ApproverAssignmentCreate, current_user: CurrentUser, db: DbSession, request: Request
) -> ApproverAssignmentRead:
    if settings.eklink_sync_enabled:
        raise HTTPException(status_code=409, detail="Assign approvers in EkLink")
    try:
        assignment = approvers.create_assignment(db, current_user, **payload.model_dump())
    except approvers.AssignmentError as exc:
        db.rollback()
        raise _http(exc) from None
    db.commit()
    db.refresh(assignment)
    audit_service.record_and_commit(
        db, request, actor=current_user, action="admin.approver_assign",
        entity_type="approver_assignment", entity_id=assignment.id,
        summary=f"Assigned {assignment.title} to {assignment.user.email}",
        details={"user_id": assignment.user_id, "title": assignment.title,
                 "scope_level": assignment.scope_level},
        organization_id=assignment.organization_id, department_id=assignment.department_id,
        institute_id_hint=assignment.institute_id,
    )
    return _assignment_read(assignment)


@router.post("/approvers/{assignment_id}/end", response_model=ApproverAssignmentRead)
def end_approver(
    assignment_id: int, current_user: CurrentUser, db: DbSession, request: Request
) -> ApproverAssignmentRead:
    assignment = db.get(ApproverAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if assignment.managed_by_eklink:
        raise HTTPException(
            status_code=409, detail=f"{MANAGED_IN_EKLINK}: end this approver job in EkLink"
        )
    try:
        approvers.end_assignment(db, current_user, assignment)
    except approvers.AssignmentError as exc:
        db.rollback()
        raise _http(exc) from None
    db.commit()
    db.refresh(assignment)
    audit_service.record_and_commit(
        db, request, actor=current_user, action="admin.approver_end",
        entity_type="approver_assignment", entity_id=assignment.id,
        summary=f"Ended {assignment.title} for {assignment.user.email}",
        organization_id=assignment.organization_id, department_id=assignment.department_id,
        institute_id_hint=assignment.institute_id,
    )
    return _assignment_read(assignment)
