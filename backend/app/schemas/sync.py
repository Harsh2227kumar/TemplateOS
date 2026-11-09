from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SyncPushResult(BaseModel):
    last_event_id: int


class SyncLinks(BaseModel):
    """EkLink Admin Console pages (None when EKLINK_URL is not set)."""

    admin: str | None = None
    users: str | None = None
    directory: str | None = None
    approvers: str | None = None


class SyncStatus(BaseModel):
    # Sync configured and not switched off: EkLink-owned data is read-only.
    enabled: bool
    configured: bool
    eklink_url: str | None = None
    eklink_admin_url: str | None = None
    links: SyncLinks
    interval_minutes: int
    full_at: str
    # The caller may press "Sync now" / "Full resync" (super_admin only).
    can_run: bool = False
    last_event_id: int = 0
    last_pull_at: datetime | None = None
    last_push_at: datetime | None = None
    last_full_sync_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    last_result: dict[str, Any] | None = None
    pending_count: int = 0


class SyncRunResult(BaseModel):
    last_event_id: int
    result: dict[str, Any] | None = None
    status: SyncStatus
