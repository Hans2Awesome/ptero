"""Main quick input parser for transaction previews."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .category_matcher import CategoryMatch, match_category
from .date_parser import parse_transaction_date
from .money_parser import MoneyParseError, parse_money


@dataclass(frozen=True)
class QuickInputResult:
    """Parsed quick input preview result."""

    type: str | None
    category_name: str | None
    amount: int | None
    note: str
    asset_name: str | None
    transaction_date: date | None
    confidence: float
    needs_review: bool
    original_text: str
    error: str | None = None


_AMOUNT_TOKEN_PATTERN = re.compile(
    r"(?i)(?:rp\s*)?\d+(?:[.,]\d+)*(?:\s*(?:k|rb|ribu|jt|juta))?"
)

_ERROR_RESULT_DEFAULTS = {
    "type": None,
    "category_name": None,
    "amount": None,
    "note": "",
    "asset_name": None,
    "transaction_date": None,
    "confidence": 0.0,
    "needs_review": True,
}


def parse_quick_input(
    text: str,
    *,
    today: date | None = None,
    timezone: str = "Asia/Jakarta",
) -> QuickInputResult:
    """Parse quick transaction text into a preview-ready result object."""
    original_text = text.strip()
    if not original_text:
        return _error_result(original_text, "Tulis transaksi dulu")

    dated = parse_transaction_date(original_text, today=today, timezone=timezone)
    text_without_date = dated.cleaned_text

    try:
        amount = parse_money(text_without_date)
    except MoneyParseError as error:
        message = str(error)
        if "lebih dari 0" in message:
            return _error_result(original_text, "Nominal harus lebih dari 0")
        return _error_result(original_text, "Nominal belum ditemukan")

    category_match = match_category(text_without_date)
    note = _build_note(text_without_date, category_match)

    return QuickInputResult(
        type=category_match.type,
        category_name=category_match.category_name,
        amount=amount,
        note=note,
        asset_name=category_match.asset_name,
        transaction_date=dated.transaction_date,
        confidence=category_match.confidence,
        needs_review=category_match.needs_review,
        original_text=original_text,
        error=None,
    )


def _error_result(original_text: str, error: str) -> QuickInputResult:
    return QuickInputResult(original_text=original_text, error=error, **_ERROR_RESULT_DEFAULTS)


def _build_note(text: str, category_match: CategoryMatch) -> str:
    cleaned = _remove_amount(text)
    cleaned = _remove_category_words(cleaned, category_match)
    cleaned = _remove_asset_words(cleaned, category_match.asset_name)
    return _normalize_spaces(cleaned)


def _remove_amount(text: str) -> str:
    return _AMOUNT_TOKEN_PATTERN.sub(" ", text, count=1)


def _remove_category_words(text: str, category_match: CategoryMatch) -> str:
    words = [category_match.category_name]
    words.extend(category_match.category_name.split())

    aliases = _category_aliases_for(category_match)
    for alias in sorted(set(aliases + words), key=len, reverse=True):
        pattern = rf"(?i)\b{re.escape(alias)}\b"
        if re.search(pattern, text):
            return re.sub(pattern, " ", text, count=1)
    return text


def _category_aliases_for(category_match: CategoryMatch) -> list[str]:
    category_aliases: dict[tuple[str, str], list[str]] = {
        ("income", "Gaji"): ["gaji", "salary"],
        ("income", "Bonus"): ["bonus"],
        ("expense", "Makan & Minum"): ["makan", "minum", "kopi", "sarapan", "makan siang", "makan malam"],
        ("expense", "Transportasi"): ["transport", "transportasi", "gojek", "grab", "bensin", "parkir"],
        ("investment", "Crypto"): ["invest", "crypto", "kripto", "btc", "eth", "bitcoin", "ethereum"],
        ("investment", "Emas"): ["emas", "gold", "antam"],
    }
    return category_aliases.get((category_match.type, category_match.category_name), [])


def _remove_asset_words(text: str, asset_name: str | None) -> str:
    if asset_name is None:
        return text

    asset_aliases = {
        "BTC": ["btc", "bitcoin"],
        "ETH": ["eth", "ethereum"],
        "Emas": ["emas", "gold", "antam"],
    }.get(asset_name, [asset_name])

    for alias in asset_aliases:
        text = re.sub(rf"(?i)\b{re.escape(alias)}\b", " ", text)
    return text


def _normalize_spaces(text: str) -> str:
    return " ".join(text.split())
