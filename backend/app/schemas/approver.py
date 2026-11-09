from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ApproverAssignmentRead(BaseModel):
    id: int
    user_id: int
    user_name: str | None = None
    user_email: str | None = None
    user_login_id: str | None = None
    title: str
    scope_level: str
    organization_id: int
    institute_id: int | None = None
    department_id: int | None = None
    scope_name: str | None = None
    scope_key: str | None = None
    valid_from: date
    valid_to: date | None = None
    is_current: bool = True
    created_at: datetime
    # 'eklink' rows are mirrored from EkLink and cannot be ended here.
    source: str = "local"
    eklink_id: str | None = None
    managed_by_eklink: bool = False


class ApproverAssignmentList(BaseModel):
    assignments: list[ApproverAssignmentRead]
    total: int
    titles: list[str]
    # False while EkLink sync is on: approvers are assigned in EkLink.
    can_create: bool = True


class ApproverAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    title: str = Field(max_length=64)
    scope_level: str = Field(max_length=20)
    organization_id: int | None = None
    institute_id: int | None = None
    department_id: int | None = None
    scope_key: str | None = Field(default=None, max_length=64)
    valid_from: date | None = None
    valid_to: date | None = None
