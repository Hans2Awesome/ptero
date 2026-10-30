"""Indonesian money amount parser for quick text input."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


class MoneyParseError(ValueError):
    """Raised when text does not contain a parseable money amount."""


_AMOUNT_PATTERN = re.compile(
    r"(?i)(?:rp\s*)?(?P<number>\d+(?:[.,]\d+)*)(?:\s*(?P<suffix>k|rb|ribu|jt|juta))?"
)

_SUFFIX_MULTIPLIERS: dict[str, int] = {
    "k": 1_000,
    "rb": 1_000,
    "ribu": 1_000,
    "jt": 1_000_000,
    "juta": 1_000_000,
}


def parse_money(text: str) -> int:
    """Parse the first Indonesian money amount found in text."""
    match = _AMOUNT_PATTERN.search(text.strip())
    if match is None:
        raise MoneyParseError("Teks tidak berisi nominal yang valid.")

    number_text = match.group("number")
    suffix = (match.group("suffix") or "").lower()
    multiplier = _SUFFIX_MULTIPLIERS.get(suffix, 1)

    try:
        amount = _parse_number(number_text, multiplier)
    except InvalidOperation as error:
        raise MoneyParseError("Teks tidak berisi nominal yang valid.") from error

    if amount <= 0:
        raise MoneyParseError("Nominal harus lebih dari 0.")
    return amount


def _parse_number(number_text: str, multiplier: int) -> int:
    if multiplier > 1:
        normalized = number_text.replace(",", ".")
        return int(Decimal(normalized) * multiplier)

    digits_only = number_text.replace(".", "").replace(",", "")
    return int(digits_only)
