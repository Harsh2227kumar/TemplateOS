from typing import Literal, get_args

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

from app.models.user import USER_ROLES

UserRole = Literal[
    "super_admin",
    "org_admin",
    "department_admin",
    "faculty",
    "student",
    "approver",
    "normal_user",
]
if set(get_args(UserRole)) != set(USER_ROLES):  # pragma: no cover - guard
    raise RuntimeError("UserRole is out of sync with app.models.user.USER_ROLES")


class UserRead(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class ProfilePreferences(BaseModel):
    default_document_format: str = "docx"
    email_notifications: bool = False


class UserMembershipMixin(BaseModel):
    """Organization / department ids plus display names from the linked rows."""

    organization_id: int | None = None
    department_id: int | None = None
    # Read from User.organization_name / department_name (the linked rows),
    # not from the legacy free-text columns.
    organization: str | None = Field(
        default=None,
        validation_alias=AliasChoices("organization_name", "organization"),
    )
    department: str | None = Field(
        default=None,
        validation_alias=AliasChoices("department_name", "department"),
    )


class UserProfileRead(UserMembershipMixin, UserRead):
    job_title: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    signature_path: str | None = None
    preferences: ProfilePreferences | None = None


def _optional_text(value: object, max_length: int, what: str) -> object:
    if value is None or not isinstance(value, str):
        return value
    cleaned = value.strip()
    if len(cleaned) > max_length:
        raise ValueError(f"{what} must be {max_length} characters or fewer")
    return cleaned or None


class UserSelfUpdate(BaseModel):
    """
    PATCH /auth/me: the ONLY fields a user may change on themselves.
    extra="forbid" makes role / organization / department (or anything
    else) a 422 instead of being silently ignored.
    """

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = None
    phone: str | None = None
    job_title: str | None = None

    @field_validator("full_name")
    @classmethod
    def _full_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Full name cannot be empty")
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Full name must contain at least 2 characters")
        if len(value) > 255:
            raise ValueError("Full name must be 255 characters or fewer")
        return value

    @field_validator("phone", mode="before")
    @classmethod
    def _phone(cls, value: object) -> object:
        return _optional_text(value, 50, "Phone")

    @field_validator("job_title", mode="before")
    @classmethod
    def _job_title(cls, value: object) -> object:
        return _optional_text(value, 255, "Job title")


# ── admin ────────────────────────────────────────────────────────────


class AdminUserRead(UserMembershipMixin, UserRead):
    # Plain str: one legacy row with an address EmailStr rejects must not
    # break the whole admin listing.
    email: str
    job_title: str | None = None
    phone: str | None = None


class AdminUserList(BaseModel):
    users: list[AdminUserRead]
    total: int
    page: int
    limit: int


class AdminUserUpdate(BaseModel):
    """
    PATCH /admin/users/{id}. Only the keys that are present are applied;
    an explicit null clears organization_id / department_id.
    """

    model_config = ConfigDict(extra="forbid")

    role: UserRole | None = None
    organization_id: int | None = None
    department_id: int | None = None

    @field_validator("role")
    @classmethod
    def _role_not_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("role cannot be null")
        return value
