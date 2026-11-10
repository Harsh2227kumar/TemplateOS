"""Time helpers."""

from datetime import datetime, timezone


def utc_now_naive() -> datetime:
    """
    Current UTC time as a NAIVE datetime.

    The DateTime columns are timezone-naive and hold UTC, and the API returns
    them as naive UTC (the frontend parses naive timestamps as UTC). This is
    the non-deprecated replacement for datetime.utcnow(): same value, same type.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
