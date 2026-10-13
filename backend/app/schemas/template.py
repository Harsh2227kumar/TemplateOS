import json
from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


def _decode_allowed_roles(value: object) -> object:
    """The DB stores allowed_roles as JSON text; the API exposes a list (or null)."""
    if value is None or isinstance(value, list):
        return value or None
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            decoded = json.loads(value)
        except ValueError:
            return None
        if isinstance(decoded, list):
            return [role for role in decoded if isinstance(role, str)] or None
        return None
    return value


class TemplateBase(BaseModel):
    name: str
    description: str | None = None
    category: str
    visibility: str


class TemplateCreate(TemplateBase):
    original_file_path: str | None = None
    original_filename: str | None = None
    file_size_bytes: int | None = None
    file_extension: str | None = None
    uploaded_by: int
    scope_organization_id: int | None = None
    scope_department_id: int | None = None
    # Legacy name copies, written alongside the ids (app/services/org_directory.py).
    scope_organization: str | None = None
    scope_department: str | None = None
    allowed_roles: str | None = None  # JSON text, as stored


class TemplateAudienceMixin(BaseModel):
    scope_organization_id: int | None = None
    scope_department_id: int | None = None
    # Display names read from the linked organizations / departments rows
    # (Template.scope_organization_name), not from the legacy string columns.
    scope_organization: str | None = Field(
        default=None,
        validation_alias=AliasChoices("scope_organization_name", "scope_organization"),
    )
    scope_department: str | None = Field(
        default=None,
        validation_alias=AliasChoices("scope_department_name", "scope_department"),
    )
    allowed_roles: list[str] | None = None
    # Computed for the requesting user (see template_access.can_manage).
    can_manage: bool = False

    @field_validator("allowed_roles", mode="before")
    @classmethod
    def _parse_allowed_roles(cls, value: object) -> object:
        return _decode_allowed_roles(value)


class TemplateResponse(TemplateAudienceMixin, TemplateBase):
    id: int
    status: str
    original_file_path: str | None = None
    processed_file_path: str | None = (
        None  # V1.3 Phase 2: cleaned copy (renderable source)
    )
    original_filename: str | None = None
    file_size_bytes: int | None = None
    uploaded_by: int
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TemplateListItem(TemplateAudienceMixin):
    id: int
    name: str
    category: str
    visibility: str
    status: str
    uploaded_by: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TemplateLibraryResponse(BaseModel):
    templates: list[TemplateListItem]
    total: int
    page: int
    limit: int

    model_config = ConfigDict(from_attributes=True)


class TemplateAccessUpdate(BaseModel):
    """PATCH /templates/{id}/access body."""

    visibility: Literal["private", "public", "organization", "department", "group"]
    scope_organization_id: int | None = None
    scope_department_id: int | None = None
    # Optional fallback for older clients: case-insensitive names of existing
    # rows. Ignored when the matching *_id is given.
    scope_organization: str | None = Field(default=None, max_length=255)
    scope_department: str | None = Field(default=None, max_length=255)
    allowed_roles: list[str] | None = None


class AccessRoleOption(BaseModel):
    value: str
    label: str


class AccessOrganizationOption(BaseModel):
    id: int
    name: str


class AccessDepartmentOption(BaseModel):
    id: int
    organization_id: int
    name: str


class AccessPublishFlags(BaseModel):
    organization: bool
    department: bool


class AccessDefaults(BaseModel):
    organization_id: int | None
    department_id: int | None


class TemplateAccessOptions(BaseModel):
    """GET /templates/access-options response."""

    roles: list[AccessRoleOption]
    organizations: list[AccessOrganizationOption]
    departments: list[AccessDepartmentOption]
    can_publish: AccessPublishFlags
    defaults: AccessDefaults
