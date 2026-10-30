"""Timezone helpers so "today" follows the user's timezone, not the server's."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Asia/Jakarta"


def resolve_timezone(name: str | None) -> ZoneInfo:
    """Return a ZoneInfo for ``name``, falling back to the project default."""

    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def now_in(name: str | None) -> datetime:
    """Return the current timezone-aware datetime in the given timezone."""

    return datetime.now(resolve_timezone(name))


def today_in(name: str | None) -> date:
    """Return the current date in the given timezone."""

    return now_in(name).date()