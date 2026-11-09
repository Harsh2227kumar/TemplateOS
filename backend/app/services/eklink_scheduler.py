"""
Background EkLink pull (SYNC_CONTRACT.md section 5.2), started from the
FastAPI lifespan (app/main.py).

- every EKLINK_SYNC_INTERVAL_MINUTES: pull changes;
- daily at EKLINK_SYNC_FULL_AT (server local time) and on the first run
  (no full sync recorded yet): full snapshot reconcile.

Off when the EkLink settings are missing, EKLINK_SYNC_ENABLED=false or the
process runs under pytest. Errors never stop the loop or the app: they are
logged and stored in sync_state.last_error by app/services/eklink_sync.py.
The blocking work runs in a worker thread.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timedelta

from app.core.config import settings

logger = logging.getLogger(__name__)

STARTUP_DELAY_SECONDS = 20


def scheduler_enabled() -> bool:
    if "pytest" in sys.modules:
        return False
    return settings.eklink_sync_enabled


def next_full_sync(now: datetime, full_at: str) -> datetime:
    hours, minutes = (int(part) for part in full_at.split(":"))
    target = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def _run(kind: str) -> None:
    from app.db.session import SessionLocal
    from app.services import eklink_sync

    with SessionLocal() as db:
        try:
            if kind == "auto":
                state = eklink_sync.get_state(db)
                kind = "full" if state.last_full_sync_at is None else "changes"
                db.commit()
            if kind == "full":
                eklink_sync.full_resync(db)
            else:
                eklink_sync.pull_changes(db)
            logger.info("EkLink sync (%s) finished", kind)
        except eklink_sync.SyncError as exc:
            logger.warning("EkLink sync (%s) failed: %s", kind, exc.detail)
        except Exception:
            logger.exception("EkLink sync (%s) failed", kind)


async def run_scheduler(stop: asyncio.Event) -> None:
    interval = settings.eklink_sync_interval_minutes * 60
    logger.warning(
        "EkLink sync scheduler on: changes every %d min, full resync daily at %s",
        settings.eklink_sync_interval_minutes,
        settings.eklink_sync_full_at,
    )
    try:
        await asyncio.wait_for(stop.wait(), timeout=STARTUP_DELAY_SECONDS)
        return
    except asyncio.TimeoutError:
        pass
    next_full = next_full_sync(datetime.now(), settings.eklink_sync_full_at)
    kind = "auto"
    while not stop.is_set():
        try:
            await asyncio.to_thread(_run, kind)
        except Exception:  # pragma: no cover - _run already swallows errors
            logger.exception("EkLink sync scheduler step failed")
        now = datetime.now()
        if now >= next_full:
            kind = "full"
            next_full = next_full_sync(now, settings.eklink_sync_full_at)
            continue
        wait = min(interval, max(1.0, (next_full - now).total_seconds()))
        try:
            await asyncio.wait_for(stop.wait(), timeout=wait)
            return
        except asyncio.TimeoutError:
            pass
        kind = "full" if datetime.now() >= next_full else "changes"
        if kind == "full":
            next_full = next_full_sync(datetime.now(), settings.eklink_sync_full_at)
