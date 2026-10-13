"""
Administration API: user management and the organization / department
directory. Mounted at /api/v1/admin.

Users (rules: app/services/user_admin.py)
  GET    /admin/users                 super_admin / org_admin / department_admin
  PATCH  /admin/users/{id}            role, organization_id, department_id

Organizations
  GET    /admin/organizations         any signed-in user (pickers need it)
  POST   /admin/organizations         super_admin
  PATCH  /admin/organizations/{id}    super_admin (rename)
  DELETE /admin/organizations/{id}    super_admin; 409 while any user or
                                      template uses it or one of its
                                      departments (unused departments are
                                      deleted with it)

Departments
  GET    /admin/departments?organization_id=
                                      super_admin: all (optionally filtered);
                                      everyone else: their own organization's
  POST   /admin/departments           super_admin anywhere, org_admin in
                                      their own organization
  PATCH  /admin/departments/{id}      same (rename)
  DELETE /admin/departments/{id}      same; 409 while any user or template
                                      uses it

Unsafe cookie requests need the CSRF header (app/core/csrf.py middleware).
"""

import logging

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession
from app.models.organization import Department, Organization
from app.models.user import USER_ROLES, User
from app.schemas.organization import (
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
)
from app.schemas.user import AdminUserList, AdminUserRead, AdminUserUpdate
from app.services.org_directory import (
    DirectoryError,
    create_department,
    create_organization,
    department_usage,
    in_use_detail,
    organization_usage,
    rename_department,
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


def _http(exc: UserAdminError | DirectoryError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ── users ────────────────────────────────────────────────────────────


@router.get("/users", response_model=AdminUserList)
def list_users(
    current_user: CurrentUser,
    db: DbSession,
    search: str | None = Query(None, max_length=100, description="Name or email"),
    role: str | None = Query(None),
    organization_id: int | None = Query(None),
    department_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> AdminUserList:
    try:
        require_user_admin(current_user)
    except UserAdminError as exc:
        raise _http(exc) from None
    if role is not None and role not in USER_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role. Allowed: {', '.join(USER_ROLES)}",
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
            )
        )
    if role is not None:
        query = query.where(User.role == role)
    if organization_id is not None:
        query = query.where(User.organization_id == organization_id)
    if department_id is not None:
        query = query.where(User.department_id == department_id)

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


@router.patch("/users/{user_id}", response_model=AdminUserRead)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> AdminUserRead:
    try:
        require_user_admin(current_user)
    except UserAdminError as exc:
        raise _http(exc) from None
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    changes = payload.model_dump(exclude_unset=True)
    try:
        apply_user_update(db, current_user, target, changes)
    except (UserAdminError, DirectoryError) as exc:
        db.rollback()
        raise _http(exc) from None
    db.commit()
    db.refresh(target)
    logger.info(
        f"User {current_user.id} updated user {target.id}: "
        f"role={target.role}, org={target.organization_id}, dept={target.department_id}"
    )
    return AdminUserRead.model_validate(target)


# ── organizations ────────────────────────────────────────────────────


def _require_super_admin(user: User, action: str) -> None:
    if user.role != "super_admin":
        raise HTTPException(
            status_code=403, detail=f"Only a super admin can {action} organizations"
        )


def _organization_read(db, organization: Organization) -> OrganizationRead:
    department_count = db.scalar(
        select(func.count(Department.id)).where(
            Department.organization_id == organization.id
        )
    )
    user_count = db.scalar(
        select(func.count(User.id)).where(User.organization_id == organization.id)
    )
    return OrganizationRead(
        id=organization.id,
        name=organization.name,
        created_at=organization.created_at,
        department_count=department_count or 0,
        user_count=user_count or 0,
    )


@router.get("/organizations", response_model=list[OrganizationRead])
def list_organizations(current_user: CurrentUser, db: DbSession) -> list[OrganizationRead]:
    department_counts = (
        select(Department.organization_id, func.count(Department.id).label("n"))
        .group_by(Department.organization_id)
        .subquery()
    )
    user_counts = (
        select(User.organization_id, func.count(User.id).label("n"))
        .where(User.organization_id.is_not(None))
        .group_by(User.organization_id)
        .subquery()
    )
    rows = db.execute(
        select(Organization, department_counts.c.n, user_counts.c.n)
        .outerjoin(
            department_counts, department_counts.c.organization_id == Organization.id
        )
        .outerjoin(user_counts, user_counts.c.organization_id == Organization.id)
        .order_by(func.lower(Organization.name))
    ).all()
    return [
        OrganizationRead(
            id=org.id,
            name=org.name,
            created_at=org.created_at,
            department_count=dept_n or 0,
            user_count=user_n or 0,
        )
        for org, dept_n, user_n in rows
    ]


@router.post(
    "/organizations",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_organization_endpoint(
    payload: OrganizationCreate, current_user: CurrentUser, db: DbSession
) -> OrganizationRead:
    _require_super_admin(current_user, "create")
    try:
        organization = create_organization(db, payload.name)
    except DirectoryError as exc:
        db.rollback()
        raise _http(exc) from None
    db.commit()
    db.refresh(organization)
    return _organization_read(db, organization)


@router.patch("/organizations/{organization_id}", response_model=OrganizationRead)
def rename_organization_endpoint(
    organization_id: int,
    payload: OrganizationUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> OrganizationRead:
    _require_super_admin(current_user, "rename")
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    try:
        rename_organization(db, organization, payload.name)
    except DirectoryError as exc:
        db.rollback()
        raise _http(exc) from None
    db.commit()
    db.refresh(organization)
    return _organization_read(db, organization)


@router.delete(
    "/organizations/{organization_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_organization_endpoint(
    organization_id: int, current_user: CurrentUser, db: DbSession
) -> Response:
    _require_super_admin(current_user, "delete")
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    users, templates = organization_usage(db, organization_id)
    if users or templates:
        raise HTTPException(
            status_code=409, detail=in_use_detail("organization", users, templates)
        )
    db.delete(organization)  # its (unused) departments cascade
    db.commit()
    logger.info(f"Super admin {current_user.id} deleted organization {organization_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── departments ──────────────────────────────────────────────────────


def _require_department_admin_for(user: User, organization_id: int | None) -> None:
    """super_admin anywhere; org_admin only inside their own organization."""
    if user.role == "super_admin":
        return
    if user.role == "org_admin":
        if user.organization_id is not None and user.organization_id == organization_id:
            return
        raise HTTPException(
            status_code=403,
            detail="You can only manage departments of your own organization",
        )
    raise HTTPException(
        status_code=403,
        detail="Only super admins and organization admins can manage departments",
    )


def _department_read(db, department: Department) -> DepartmentRead:
    user_count = db.scalar(
        select(func.count(User.id)).where(User.department_id == department.id)
    )
    return DepartmentRead(
        id=department.id,
        organization_id=department.organization_id,
        name=department.name,
        created_at=department.created_at,
        user_count=user_count or 0,
    )


@router.get("/departments", response_model=list[DepartmentRead])
def list_departments(
    current_user: CurrentUser,
    db: DbSession,
    organization_id: int | None = Query(None),
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
            name=dept.name,
            created_at=dept.created_at,
            user_count=n or 0,
        )
        for dept, n in rows
    ]


@router.post(
    "/departments", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED
)
def create_department_endpoint(
    payload: DepartmentCreate, current_user: CurrentUser, db: DbSession
) -> DepartmentRead:
    organization_id = payload.organization_id
    if organization_id is None and current_user.role == "org_admin":
        organization_id = current_user.organization_id
    if organization_id is None and current_user.role == "super_admin":
        raise HTTPException(status_code=422, detail="organization_id is required")
    _require_department_admin_for(current_user, organization_id)
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(
            status_code=422, detail=f"Organization {organization_id} does not exist"
        )
    try:
        department = create_department(db, organization, payload.name)
    except DirectoryError as exc:
        db.rollback()
        raise _http(exc) from None
    db.commit()
    db.refresh(department)
    return _department_read(db, department)


def _get_department_or_404(db, department_id: int) -> Department:
    department = db.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return department


@router.patch("/departments/{department_id}", response_model=DepartmentRead)
def rename_department_endpoint(
    department_id: int,
    payload: DepartmentUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> DepartmentRead:
    department = _get_department_or_404(db, department_id)
    _require_department_admin_for(current_user, department.organization_id)
    try:
        rename_department(db, department, payload.name)
    except DirectoryError as exc:
        db.rollback()
        raise _http(exc) from None
    db.commit()
    db.refresh(department)
    return _department_read(db, department)


@router.delete("/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department_endpoint(
    department_id: int, current_user: CurrentUser, db: DbSession
) -> Response:
    department = _get_department_or_404(db, department_id)
    _require_department_admin_for(current_user, department.organization_id)
    users, templates = department_usage(db, department_id)
    if users or templates:
        raise HTTPException(
            status_code=409, detail=in_use_detail("department", users, templates)
        )
    db.delete(department)
    db.commit()
    logger.info(f"User {current_user.id} deleted department {department_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
