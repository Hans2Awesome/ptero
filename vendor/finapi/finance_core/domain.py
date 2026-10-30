"""Domain types and constants for the Finance API."""

from __future__ import annotations

try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """Fallback for Python < 3.11."""
        def __str__(self) -> str:
            return str(self.value)


class TransactionType(StrEnum):
    """Supported transaction type values."""

    INCOME = "income"
    EXPENSE = "expense"
    INVESTMENT = "investment"


_TRANSACTION_TYPE_LABELS: dict[TransactionType, str] = {
    TransactionType.INCOME: "Pemasukan",
    TransactionType.EXPENSE: "Pengeluaran",
    TransactionType.INVESTMENT: "Investasi",
}


def valid_transaction_type_values() -> set[str]:
    """Return all supported transaction type values."""
    return {t.value for t in TransactionType}


def transaction_type_label(transaction_type: TransactionType | str) -> str:
    """Return the Indonesian display label for a transaction type."""
    return _TRANSACTION_TYPE_LABELS[TransactionType(transaction_type)]
