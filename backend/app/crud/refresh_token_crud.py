"""
Refresh-token persistence: issue, rotate (with reuse detection), revoke and
clean up. Raw tokens never touch the database; only their SHA-256 hash does.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.refresh_token import RefreshToken

# 32 random bytes -> 43 url-safe characters; anything far outside that range
# is rejected before hashing/querying.
_MAX_TOKEN_LENGTH = 256


def _utcnow() -> datetime:
    """Naive UTC, matching the DateTime columns used across the schema."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IssuedRefreshToken:
    token: str
    record: RefreshToken


class RotationStatus(str, Enum):
    ROTATED = "rotated"
    INVALID = "invalid"  # unknown, malformed or expired
    REUSED = "reused"  # a revoked token was presented; family revoked
    # Rotated moments ago (another tab / concurrent request won the race);
    # the caller already holds the replacement. Nothing revoked.
    ALREADY_ROTATED = "already_rotated"


@dataclass(frozen=True)
class RotationResult:
    status: RotationStatus
    issued: IssuedRefreshToken | None = None


def issue_refresh_token(
    db: Session, user_id: int, family_id: str | None = None
) -> IssuedRefreshToken:
    """Create (and flush, not commit) a new refresh token row."""
    token = secrets.token_urlsafe(32)
    now = _utcnow()
    record = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(token),
        family_id=family_id or uuid.uuid4().hex,
        created_at=now,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(record)
    db.flush()
    return IssuedRefreshToken(token=token, record=record)


def get_by_token(db: Session, token: str | None) -> RefreshToken | None:
    if not token or len(token) > _MAX_TOKEN_LENGTH:
        return None
    return db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(token)
        )
    )


def revoke_family(db: Session, family_id: str) -> int:
    result = db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_utcnow())
    )
    return result.rowcount or 0


def rotate_refresh_token(db: Session, token: str | None) -> RotationResult:
    """
    Validate `token` and swap it for a new one in the same family.

    The old row is revoked with a conditional UPDATE (`revoked_at IS NULL`),
    so two concurrent rotations of the same token cannot both succeed.

    Presenting an already-revoked token is reuse (family revoked) unless it
    was rotated within REFRESH_REUSE_GRACE_SECONDS and the family is still
    live: then ALREADY_ROTATED is returned and nothing changes, because
    browser tabs share cookies and the loser already holds the replacement.
    The concurrent-race loser gets the same treatment. Commits.
    """
    record = get_by_token(db, token)
    if record is None:
        return RotationResult(RotationStatus.INVALID)

    if record.revoked_at is not None:
        return _handle_revoked(db, record)

    now = _utcnow()
    if record.expires_at <= now:
        return RotationResult(RotationStatus.INVALID)

    claimed = db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == record.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    if not claimed.rowcount:
        # Lost a race with a concurrent rotation; re-read what the winner
        # committed and apply the same grace rule.
        db.rollback()
        db.refresh(record)
        return _handle_revoked(db, record)

    issued = issue_refresh_token(db, record.user_id, family_id=record.family_id)
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == record.id)
        .values(replaced_by_id=issued.record.id)
    )
    db.commit()
    return RotationResult(RotationStatus.ROTATED, issued)


def _within_rotation_grace(db: Session, record: RefreshToken) -> bool:
    """
    True when `record` was revoked by rotation (not logout / family
    revocation) less than REFRESH_REUSE_GRACE_SECONDS ago and its family
    still has a live token, i.e. the session itself is intact.
    """
    if record.revoked_at is None or record.replaced_by_id is None:
        return False
    now = _utcnow()
    grace = timedelta(seconds=settings.refresh_reuse_grace_seconds)
    if now - record.revoked_at > grace:
        return False
    live = db.scalar(
        select(RefreshToken.id).where(
            RefreshToken.family_id == record.family_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
    )
    return live is not None


def _handle_revoked(db: Session, record: RefreshToken) -> RotationResult:
    if _within_rotation_grace(db, record):
        return RotationResult(RotationStatus.ALREADY_ROTATED)
    revoke_family(db, record.family_id)
    db.commit()
    return RotationResult(RotationStatus.REUSED)


def revoke_refresh_token(db: Session, token: str | None) -> bool:
    """
    Logout: revoke the presented token and anything still live in its
    family (normally nothing else). Commits. Returns whether a token matched.
    """
    record = get_by_token(db, token)
    if record is None:
        return False
    revoke_family(db, record.family_id)
    db.commit()
    return True


def delete_expired_refresh_tokens(db: Session) -> int:
    """
    Opportunistic cleanup (called on login). Only expired rows go: revoked
    but unexpired rows must stay so reuse of a stolen token is still detected.
    Does not commit.
    """
    result = db.execute(
        delete(RefreshToken).where(RefreshToken.expires_at <= _utcnow())
    )
    return result.rowcount or 0
