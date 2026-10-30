"""Lightweight Indonesian date parser for quick transaction input."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    except ImportError:
        ZoneInfo = None  # type: ignore


@dataclass(frozen=True)
class ParsedDate:
    """Parsed transaction date and text with date tokens removed."""

    transaction_date: date
    cleaned_text: str


_ISO_DATE_PATTERN = re.compile(r"\b(?P<date>\d{4}-\d{2}-\d{2})\b")
_SLASH_DATE_PATTERN = re.compile(r"\b(?P<date>\d{2}/\d{2}/\d{4})\b")


def parse_transaction_date(
    text: str,
    *,
    today: date | None = None,
    timezone: str = "Asia/Jakarta",
) -> ParsedDate:
    """Parse supported Indonesian date tokens from quick input text."""
    if today is not None:
        effective_today = today
    elif ZoneInfo is not None:
        try:
            effective_today = datetime.now(ZoneInfo(timezone)).date()
        except Exception:
            effective_today = datetime.now().date()
    else:
        effective_today = datetime.now().date()

    transaction_date = effective_today
    cleaned_text = text

    iso_match = _ISO_DATE_PATTERN.search(cleaned_text)
    slash_match = _SLASH_DATE_PATTERN.search(cleaned_text)

    if iso_match is not None:
        transaction_date = date.fromisoformat(iso_match.group("date"))
        cleaned_text = _remove_span(cleaned_text, iso_match.span())
    elif slash_match is not None:
        transaction_date = datetime.strptime(slash_match.group("date"), "%d/%m/%Y").date()
        cleaned_text = _remove_span(cleaned_text, slash_match.span())
    elif re.search(r"(?i)\bhari\s+ini\b", cleaned_text):
        cleaned_text = re.sub(r"(?i)\bhari\s+ini\b", " ", cleaned_text, count=1)
    elif re.search(r"(?i)\bkemarin\b", cleaned_text):
        transaction_date = effective_today - timedelta(days=1)
        cleaned_text = re.sub(r"(?i)\bkemarin\b", " ", cleaned_text, count=1)

    return ParsedDate(
        transaction_date=transaction_date,
        cleaned_text=_normalize_spaces(cleaned_text),
    )


def _remove_span(text: str, span: tuple[int, int]) -> str:
    start, end = span
    return f"{text[:start]} {text[end:]}"


def _normalize_spaces(text: str) -> str:
    return " ".join(text.split())
