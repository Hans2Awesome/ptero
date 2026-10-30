"""Date range helpers for reports."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class DateRange:
    """Inclusive date range for reports."""

    start_date: date
    end_date: date


def today_range(current_date: date) -> DateRange:
    """Return the inclusive range for a daily report."""
    return DateRange(start_date=current_date, end_date=current_date)


def week_range(current_date: date) -> DateRange:
    """Return the Monday-Sunday inclusive range for the given date."""
    start_date = current_date - timedelta(days=current_date.weekday())
    end_date = start_date + timedelta(days=6)
    return DateRange(start_date=start_date, end_date=end_date)


def month_range(current_date: date) -> DateRange:
    """Return the inclusive range from the first to last day of a month."""
    last_day = calendar.monthrange(current_date.year, current_date.month)[1]
    return DateRange(
        start_date=date(current_date.year, current_date.month, 1),
        end_date=date(current_date.year, current_date.month, last_day),
    )
