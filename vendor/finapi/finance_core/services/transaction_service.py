"""Transaction services shared by the API and the Telegram bot."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..db.connection import transaction as transaction_scope
from ..db.transactions import Transaction, create_transaction
from .quick_input_parser import QuickInputResult


class TransactionServiceError(ValueError):
    """Raised when a transaction cannot be saved."""


@dataclass(frozen=True)
class SavedTransactionSummary:
    """Summary of a transaction saved from a confirmed preview."""

    id: int
    type: str
    category_name: str
    amount: int
    note: str | None
    asset_name: str | None
    transaction_date: str


def find_category_id(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    category_type: str,
    category_name: str,
) -> int | None:
    """Return the category ID matching a user's category name and type."""

    row = connection.execute(
        """
        SELECT id FROM categories
        WHERE user_id = ? AND type = ? AND LOWER(name) = LOWER(?)
        """,
        (user_id, category_type, category_name),
    ).fetchone()
    return None if row is None else int(row["id"])


def find_or_create_category(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    category_type: str,
    category_name: str,
) -> int:
    """Find a category by name/type or create it for this user."""

    existing_id = find_category_id(
        connection,
        user_id=user_id,
        category_type=category_type,
        category_name=category_name,
    )
    if existing_id is not None:
        return existing_id

    cursor = connection.execute(
        """
        INSERT INTO categories (user_id, type, name, aliases, is_default)
        VALUES (?, ?, ?, '', 0)
        """,
        (user_id, category_type, category_name.strip()),
    )
    return int(cursor.lastrowid)


def save_quick_input_transaction(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    preview: QuickInputResult,
) -> Transaction:
    """Save a confirmed quick-input preview, creating the category if needed."""

    validated = _require_valid_preview(preview)
    with transaction_scope(connection):
        category_id = find_or_create_category(
            connection,
            user_id=user_id,
            category_type=validated.type,
            category_name=validated.category_name,
        )
        return create_transaction(
            connection,
            user_id=user_id,
            type=validated.type,
            category_id=category_id,
            amount=validated.amount,
            note=validated.note or None,
            asset_name=validated.asset_name,
            transaction_date=validated.transaction_date,
        )


def save_confirmed_transaction(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    preview: QuickInputResult,
) -> SavedTransactionSummary:
    """Save a confirmed preview using an existing category only (bot flow)."""

    validated = _require_valid_preview(preview)
    category_id = find_category_id(
        connection,
        user_id=user_id,
        category_type=validated.type,
        category_name=validated.category_name,
    )
    if category_id is None:
        raise TransactionServiceError("Kategori tidak valid untuk user ini.")

    with transaction_scope(connection):
        transaction = create_transaction(
            connection,
            user_id=user_id,
            type=validated.type,
            category_id=category_id,
            amount=validated.amount,
            note=validated.note or None,
            asset_name=validated.asset_name,
            transaction_date=validated.transaction_date,
        )
    return SavedTransactionSummary(
        id=transaction.id,
        type=transaction.type,
        category_name=validated.category_name,
        amount=transaction.amount,
        note=transaction.note,
        asset_name=transaction.asset_name,
        transaction_date=transaction.transaction_date,
    )


@dataclass(frozen=True)
class _ValidatedPreview:
    type: str
    category_name: str
    amount: int
    note: str
    asset_name: str | None
    transaction_date: str


def _require_valid_preview(preview: QuickInputResult) -> _ValidatedPreview:
    if preview.error or (
        preview.type is None
        or preview.category_name is None
        or preview.amount is None
        or preview.transaction_date is None
    ):
        raise TransactionServiceError("Preview belum valid dan belum bisa disimpan.")

    return _ValidatedPreview(
        type=preview.type,
        category_name=preview.category_name,
        amount=preview.amount,
        note=preview.note,
        asset_name=preview.asset_name,
        transaction_date=preview.transaction_date.isoformat(),
    )