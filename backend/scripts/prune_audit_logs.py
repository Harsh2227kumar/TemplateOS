"""
Retention for the V1.7 Phase 3 trails: delete audit_logs older than
AUDIT_RETENTION_DAYS and download_history older than
DOWNLOAD_HISTORY_RETENTION_DAYS, in batches of 1000.

Dry run by default (counts only). Deleting needs --yes.

    python scripts/prune_audit_logs.py          # how many rows would go
    python scripts/prune_audit_logs.py --yes    # delete them
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.clock import utc_now_naive  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.download_history import DownloadHistory  # noqa: E402

BATCH_SIZE = 1000


@dataclass
class PruneResult:
    audit_logs: int
    download_history: int


def _prune_table(db: Session, model, timestamp, cutoff: datetime, dry_run: bool) -> int:
    if dry_run:
        return db.scalar(select(func.count()).select_from(model).where(timestamp < cutoff)) or 0
    removed = 0
    while True:
        ids = db.scalars(select(model.id).where(timestamp < cutoff).order_by(model.id).limit(BATCH_SIZE)).all()
        if not ids:
            return removed
        db.execute(delete(model).where(model.id.in_(ids)))
        db.commit()
        removed += len(ids)


def prune(
    db: Session,
    *,
    now: datetime | None = None,
    audit_days: int | None = None,
    download_days: int | None = None,
    dry_run: bool = True,
) -> PruneResult:
    now = now or utc_now_naive()
    audit_cutoff = now - timedelta(days=audit_days or settings.audit_retention_days)
    download_cutoff = now - timedelta(days=download_days or settings.download_history_retention_days)
    return PruneResult(
        audit_logs=_prune_table(db, AuditLog, AuditLog.created_at, audit_cutoff, dry_run),
        download_history=_prune_table(
            db, DownloadHistory, DownloadHistory.downloaded_at, download_cutoff, dry_run
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete audit and download rows past their retention")
    parser.add_argument("--yes", action="store_true", help="delete (without it: dry run, counts only)")
    args = parser.parse_args()

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        result = prune(db, dry_run=not args.yes)
    verb = "Deleted" if args.yes else "Would delete"
    print(
        f"{verb} {result.audit_logs} audit log row(s) older than {settings.audit_retention_days} days "
        f"and {result.download_history} download row(s) older than "
        f"{settings.download_history_retention_days} days."
    )
    if not args.yes:
        print("Dry run. Re-run with --yes to delete.")


if __name__ == "__main__":
    main()
