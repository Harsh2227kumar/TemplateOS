"""
V1.7 Phase 3 - download history and audit log schemas.

- DownloadHistoryItem   GET /me/downloads, GET /documents/{id}/downloads
- AuditLogItem          GET /admin/audit-logs (details parsed to a dict)
- AuditActionOption     GET /admin/audit-logs/actions
- Paginated[T]          {items, total, page, limit}
"""

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, field_validator

from app.crud.audit_log_crud import decode_details

T = TypeVar("T")


class Paginated(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    limit: int


class DownloadHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    downloaded_at: datetime
    format: Literal["docx", "pdf"]
    document_id: int | None = None
    document_name: str
    version: int | None = None
    version_source: str | None = None
    file_name: str
    file_size: int | None = None
    # False once the document was deleted (the name above is a snapshot).
    document_exists: bool


class AuditLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    actor_id: int | None = None
    actor_email: str | None = None
    action: str
    entity_type: str
    entity_id: int | None = None
    summary: str
    details: dict[str, Any] | None = None
    ip_address: str | None = None

    @field_validator("details", mode="before")
    @classmethod
    def _parse_details(cls, value: Any) -> Any:
        return decode_details(value) if isinstance(value, str) or value is None else value


class AuditActionOption(BaseModel):
    action: str
    label: str
    area: str
