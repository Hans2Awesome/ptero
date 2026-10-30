"""Transaction repository shared by the API and the Telegram bot."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

_SELECT = """
    SELECT t.id, t.user_id, t.type, t.category_id, c.name AS category_name,
           t.amount, t.note, t.asset_name, t.transaction_date
    FROM transactions t
    LEFT JOIN categories c ON t.category_id = c.id
"""


@dataclass(frozen=True)
class Transaction:
    """A financial transaction persisted in SQLite."""

    id: int
    user_id: int
    type: str
    category_id: int | None
    amount: int
    note: str | None
    asset_name: str | None
    transaction_date: str
    category_name: str | None = None


def _row_to_transaction(row: sqlite3.Row) -> Transaction:
    keys = row.keys()
    return Transaction(
        id=row["id"],
        user_id=row["user_id"],
        type=row["type"],
        category_id=row["category_id"],
        amount=row["amount"],
        note=row["note"],
        asset_name=row["asset_name"],
        transaction_date=row["transaction_date"],
        category_name=row["category_name"] if "category_name" in keys else None,
    )


def create_transaction(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    type: str,
    category_id: int | None,
    amount: int,
    note: str | None,
    asset_name: str | None,
    transaction_date: str,
) -> Transaction:
    """Create and return a transaction for one user."""

    cursor = connection.execute(
        """
        INSERT INTO transactions (
            user_id, type, category_id, amount, note, asset_name, transaction_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, type, category_id, amount, note, asset_name, transaction_date),
    )

    transaction = get_transaction_by_id(
        connection,
        user_id=user_id,
        transaction_id=cursor.lastrowid,
    )
    if transaction is None:
        raise RuntimeError("Failed to create transaction")
    return transaction


def get_transaction_by_id(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    transaction_id: int,
) -> Transaction | None:
    """Fetch one owned transaction with its category name."""

    row = connection.execute(
        _SELECT + " WHERE t.id = ? AND t.user_id = ?",
        (transaction_id, user_id),
    ).fetchone()
    return None if row is None else _row_to_transaction(row)


def list_transactions(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Transaction]:
    """List owned transactions, newest first, with optional filters."""

    query = _SELECT + " WHERE t.user_id = ?"
    params: list = [user_id]

    if start_date:
        query += " AND t.transaction_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND t.transaction_date <= ?"
        params.append(end_date)
    if transaction_type:
        query += " AND t.type = ?"
        params.append(transaction_type)

    query += " ORDER BY t.transaction_date DESC, t.id DESC"
    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    rows = connection.execute(query, tuple(params)).fetchall()
    return [_row_to_transaction(row) for row in rows]


def list_transactions_by_type(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    transaction_type: str,
    limit: int,
    offset: int = 0,
) -> list[Transaction]:
    """List owned transactions of one type, newest first, paginated."""

    return list_transactions(
        connection,
        user_id=user_id,
        transaction_type=transaction_type,
        limit=limit,
        offset=offset,
    )


def count_transactions_by_type(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    transaction_type: str,
) -> int:
    """Count owned transactions of one type."""

    row = connection.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id = ? AND type = ?",
        (user_id, transaction_type),
    ).fetchone()
    return int(row[0])


def list_transactions_in_range(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    start_date: str,
    end_date: str,
) -> list[Transaction]:
    """List owned transactions in an inclusive range, oldest first."""

    rows = connection.execute(
        _SELECT
        + """
        WHERE t.user_id = ? AND t.transaction_date BETWEEN ? AND ?
        ORDER BY t.transaction_date ASC, t.id ASC
        """,
        (user_id, start_date, end_date),
    ).fetchall()
    return [_row_to_transaction(row) for row in rows]


def update_transaction(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    transaction_id: int,
    amount: int | None = None,
    category_id: int | None = None,
    transaction_date: str | None = None,
    note: str | None = None,
    asset_name: str | None = None,
) -> Transaction | None:
    """Update editable fields for an owned transaction."""

    current = get_transaction_by_id(connection, user_id=user_id, transaction_id=transaction_id)
    if current is None:
        return None

    connection.execute(
        """
        UPDATE transactions
        SET amount = ?, category_id = ?, transaction_date = ?, note = ?, asset_name = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (
            amount if amount is not None else current.amount,
            category_id if category_id is not None else current.category_id,
            transaction_date if transaction_date is not None else current.transaction_date,
            note if note is not None else current.note,
            asset_name if asset_name is not None else current.asset_name,
            transaction_id,
            user_id,
        ),
    )
    return get_transaction_by_id(connection, user_id=user_id, transaction_id=transaction_id)


def delete_transaction(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    transaction_id: int,
) -> bool:
    """Delete one owned transaction."""

    cursor = connection.execute(
        "DELETE FROM transactions WHERE id = ? AND user_id = ?",
        (transaction_id, user_id),
    )
    return cursor.rowcount > 0
