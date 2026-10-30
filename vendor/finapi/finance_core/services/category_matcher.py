"""Alias-based category matcher for quick transaction input."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..db.categories import DEFAULT_CATEGORIES
from ..domain import TransactionType


@dataclass(frozen=True)
class CategoryMatch:
    """Matched transaction category and review metadata."""

    type: str
    category_name: str
    asset_name: str | None
    confidence: float
    needs_review: bool


_INVESTMENT_ASSET_ALIASES: dict[str, str] = {
    "btc": "BTC",
    "bitcoin": "BTC",
    "eth": "ETH",
    "ethereum": "ETH",
    "bbca": "BBCA",
    "bmri": "BMRI",
    "emas": "Emas",
    "gold": "Emas",
    "antam": "Emas",
}


def match_category(text: str) -> CategoryMatch:
    """Match text to a default category using category aliases."""
    normalized_text = _normalize_text(text)
    tokens = set(normalized_text.split())

    best_match: CategoryMatch | None = None
    best_score = 0

    for transaction_type, category_name, aliases in DEFAULT_CATEGORIES:
        for alias in _alias_values(aliases):
            score = _alias_score(normalized_text, tokens, alias)
            if score > best_score:
                best_score = score
                best_match = CategoryMatch(
                    transaction_type.value,
                    category_name,
                    asset_name=_detect_asset(transaction_type, normalized_text),
                    confidence=1.0,
                    needs_review=False,
                )

    if best_match is not None:
        return best_match

    return CategoryMatch(
        TransactionType.EXPENSE.value,
        "Lainnya",
        asset_name=None,
        confidence=0.0,
        needs_review=True,
    )


def _alias_values(aliases: str) -> list[str]:
    return [_normalize_text(alias) for alias in aliases.split(",") if alias.strip()]


def _alias_score(normalized_text: str, tokens: set[str], alias: str) -> int:
    if " " in alias:
        return len(alias.split()) if re.search(rf"\b{re.escape(alias)}\b", normalized_text) else 0
    return 1 if alias in tokens else 0


def _detect_asset(transaction_type: TransactionType, normalized_text: str) -> str | None:
    if transaction_type is not TransactionType.INVESTMENT:
        return None

    tokens = set(normalized_text.split())
    for alias, asset_name in _INVESTMENT_ASSET_ALIASES.items():
        if alias in tokens:
            return asset_name
    return None


def _normalize_text(text: str) -> str:
    lowered = text.casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", lowered).split())
