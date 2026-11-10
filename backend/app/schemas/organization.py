from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrganizationRead(BaseModel):
    id: int
    name: str
    code: str | None = None
    is_active: bool = True
    is_demo: bool = False
    # Has a code: mirrored from EkLink and read-only here.
    managed_by_eklink: bool = False
    created_at: datetime
    institute_count: int = 0
    department_count: int = 0
    user_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=255)
    code: str | None = Field(default=None, max_length=32)


class OrganizationUpdate(BaseModel):
    """Rename and / or change the code or the active flag (keys present only)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)
    code: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None


class InstituteRead(BaseModel):
    id: int
    organization_id: int
    name: str
    code: str | None = None
    is_active: bool = True
    is_demo: bool = False
    # Has a code: mirrored from EkLink and read-only here.
    managed_by_eklink: bool = False
    created_at: datetime
    department_count: int = 0
    user_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class InstituteCreate(BaseModel):
    """organization_id may be omitted by an org_admin (defaults to their own)."""

    model_config = ConfigDict(extra="forbid")

    organization_id: int | None = None
    name: str = Field(max_length=255)
    code: str | None = Field(default=None, max_length=32)


class InstituteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)
    code: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None


class DepartmentRead(BaseModel):
    id: int
    organization_id: int
    institute_id: int | None = None
    name: str
    code: str | None = None
    is_active: bool = True
    is_demo: bool = False
    # Has a code: mirrored from EkLink and read-only here.
    managed_by_eklink: bool = False
    created_at: datetime
    user_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class DepartmentCreate(BaseModel):
    """organization_id / institute_id may be omitted when the caller's own
    scope (or the institute) implies them."""

    model_config = ConfigDict(extra="forbid")

    organization_id: int | None = None
    institute_id: int | None = None
    name: str = Field(max_length=255)
    code: str | None = Field(default=None, max_length=32)


class DepartmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)
    code: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None
