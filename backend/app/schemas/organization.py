from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrganizationRead(BaseModel):
    id: int
    name: str
    created_at: datetime
    department_count: int = 0
    user_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=255)


class OrganizationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=255)


class DepartmentRead(BaseModel):
    id: int
    organization_id: int
    name: str
    created_at: datetime
    user_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class DepartmentCreate(BaseModel):
    """organization_id may be omitted by an org_admin (defaults to their own)."""

    model_config = ConfigDict(extra="forbid")

    organization_id: int | None = None
    name: str = Field(max_length=255)


class DepartmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=255)
