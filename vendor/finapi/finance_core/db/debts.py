"""Debt/Receivable repository for the Finance API."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional

from .connection import transaction


@dataclass(frozen=True)
class Debt:
    """A debt or receivable record persisted in SQLite."""

    id: int
    user_id: int
    type: str  # 'debt' or 'receivable'
    person_name: str
    total_amount: int
    paid_amount: int
    note: Optional[str]
    due_date: Optional[str]
    status: str  # 'active' or 'settled'
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(frozen=True)
class DebtPayment:
    """A single installment payment for a debt/receivable."""

    id: int
    debt_id: int
    amount: int
    note: Optional[str]
    payment_date: str
    created_at: Optional[str] = None


def _row_to_debt(row: sqlite3.Row) -> Debt:
    return Debt(
        id=row["id"],
        user_id=row["user_id"],
        type=row["type"],
        person_name=row["person_name"],
        total_amount=row["total_amount"],
        paid_amount=row["paid_amount"],
        note=row["note"],
        due_date=row["due_date"],
        status=row["status"],
        created_at=row["created_at"] if "created_at" in row.keys() else None,
        updated_at=row["updated_at"] if "updated_at" in row.keys() else None,
    )


def _row_to_payment(row: sqlite3.Row) -> DebtPayment:
    return DebtPayment(
        id=row["id"],
        debt_id=row["debt_id"],
        amount=row["amount"],
        note=row["note"],
        payment_date=row["payment_date"],
        created_at=row["created_at"] if "created_at" in row.keys() else None,
    )


# ---------------------------------------------------------------------------
# Debt CRUD
# ---------------------------------------------------------------------------


def create_debt(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    type: str,
    person_name: str,
    total_amount: int,
    note: str | None = None,
    due_date: str | None = None,
) -> Debt:
    """Create a new debt/receivable record."""
    connection.row_factory = sqlite3.Row
    cursor = connection.execute(
        """
        INSERT INTO debts (user_id, type, person_name, total_amount, note, due_date)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, type, person_name, total_amount, note, due_date),
    )
    debt_id = cursor.lastrowid
    debt = get_debt_by_id(connection, user_id=user_id, debt_id=debt_id)
    if debt is None:
        raise RuntimeError("Failed to create debt record")
    return debt


def get_debt_by_id(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    debt_id: int,
) -> Debt | None:
    """Fetch one debt by ID owned by user."""
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        """
        SELECT id, user_id, type, person_name, total_amount, paid_amount,
               note, due_date, status, created_at, updated_at
        FROM debts
        WHERE id = ? AND user_id = ?
        """,
        (debt_id, user_id),
    ).fetchone()
    if row is None:
        return None
    return _row_to_debt(row)


def list_debts(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    debt_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Debt]:
    """List debts/receivables with optional filters."""
    connection.row_factory = sqlite3.Row

    query = """
        SELECT id, user_id, type, person_name, total_amount, paid_amount,
               note, due_date, status, created_at, updated_at
        FROM debts
        WHERE user_id = ?
    """
    params: list = [user_id]

    if debt_type:
        query += " AND type = ?"
        params.append(debt_type)
    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY CASE WHEN status = 'active' THEN 0 ELSE 1 END, due_date ASC NULLS LAST, created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = connection.execute(query, tuple(params)).fetchall()
    return [_row_to_debt(r) for r in rows]


def update_debt(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    debt_id: int,
    person_name: str | None = None,
    total_amount: int | None = None,
    note: str | None = None,
    due_date: str | None = None,
    status: str | None = None,
) -> Debt | None:
    """Update editable fields for an owned debt."""
    current = get_debt_by_id(connection, user_id=user_id, debt_id=debt_id)
    if current is None:
        return None

    new_person = person_name if person_name is not None else current.person_name
    new_total = total_amount if total_amount is not None else current.total_amount

    if new_total < current.paid_amount:
        raise ValueError("Total hutang/piutang tidak boleh lebih kecil dari jumlah yang sudah dibayar.")
    new_note = note if note is not None else current.note
    new_due = due_date if due_date is not None else current.due_date
    new_status = status if status is not None else current.status

    connection.execute(
        """
        UPDATE debts
        SET person_name = ?, total_amount = ?, note = ?, due_date = ?, status = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (new_person, new_total, new_note, new_due, new_status, debt_id, user_id),
    )
    return get_debt_by_id(connection, user_id=user_id, debt_id=debt_id)


def delete_debt(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    debt_id: int,
) -> bool:
    """Delete one owned debt/receivable and its payments."""
    cursor = connection.execute(
        "DELETE FROM debts WHERE id = ? AND user_id = ?",
        (debt_id, user_id),
    )
    return cursor.rowcount > 0


def get_debt_summary(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    today: str,
) -> dict:
    """Get aggregated summary of active debts and receivables.

    ``today`` is the user's local date (YYYY-MM-DD) so reminders follow the
    user's timezone instead of the server's UTC clock.
    """

    row = connection.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN type = 'debt' AND status = 'active' THEN total_amount - paid_amount ELSE 0 END), 0) AS total_debt_remaining,
            COALESCE(SUM(CASE WHEN type = 'receivable' AND status = 'active' THEN total_amount - paid_amount ELSE 0 END), 0) AS total_receivable_remaining,
            COALESCE(SUM(CASE WHEN type = 'debt' AND status = 'active' THEN 1 ELSE 0 END), 0) AS active_debt_count,
            COALESCE(SUM(CASE WHEN type = 'receivable' AND status = 'active' THEN 1 ELSE 0 END), 0) AS active_receivable_count,
            COALESCE(SUM(CASE WHEN status = 'active' AND due_date IS NOT NULL AND due_date <= date(?, '+7 days') AND due_date >= ? THEN 1 ELSE 0 END), 0) AS due_soon_count
        FROM debts
        WHERE user_id = ?
        """,
        (today, today, user_id),
    ).fetchone()

    return {
        "total_debt_remaining": row["total_debt_remaining"],
        "total_receivable_remaining": row["total_receivable_remaining"],
        "active_debt_count": row["active_debt_count"],
        "active_receivable_count": row["active_receivable_count"],
        "due_soon_count": row["due_soon_count"],
    }


# ---------------------------------------------------------------------------
# Debt Payment CRUD
# ---------------------------------------------------------------------------


def create_debt_payment(
    connection: sqlite3.Connection,
    *,
    debt_id: int,
    user_id: int,
    amount: int,
    note: str | None = None,
    payment_date: str,
) -> DebtPayment:
    """Record an installment payment for a debt/receivable."""
    connection.row_factory = sqlite3.Row

    # Verify ownership
    debt = get_debt_by_id(connection, user_id=user_id, debt_id=debt_id)
    if debt is None:
        raise ValueError("Hutang/piutang tidak ditemukan.")
    if debt.status == "settled":
        raise ValueError("Hutang/piutang sudah lunas.")

    remaining = debt.total_amount - debt.paid_amount
    if amount > remaining:
        raise ValueError("Nominal pembayaran melebihi sisa hutang/piutang.")

    with transaction(connection):
        cursor = connection.execute(
            """
            INSERT INTO debt_payments (debt_id, amount, note, payment_date)
            VALUES (?, ?, ?, ?)
            """,
            (debt_id, amount, note, payment_date),
        )

        # Update paid_amount on the debt
        new_paid = debt.paid_amount + amount
        new_status = "settled" if new_paid >= debt.total_amount else "active"
        connection.execute(
            """
            UPDATE debts
            SET paid_amount = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_paid, new_status, debt_id),
        )

    payment_id = cursor.lastrowid
    payment = connection.execute(
        """
        SELECT id, debt_id, amount, note, payment_date, created_at
        FROM debt_payments
        WHERE id = ?
        """,
        (payment_id,),
    ).fetchone()
    if payment is None:
        raise RuntimeError("Failed to create payment record")
    return _row_to_payment(payment)


def list_debt_payments(
    connection: sqlite3.Connection,
    *,
    debt_id: int,
    user_id: int,
) -> list[DebtPayment]:
    """List all payments for one debt (verify ownership)."""
    connection.row_factory = sqlite3.Row

    # Verify ownership
    debt = get_debt_by_id(connection, user_id=user_id, debt_id=debt_id)
    if debt is None:
        return []

    rows = connection.execute(
        """
        SELECT id, debt_id, amount, note, payment_date, created_at
        FROM debt_payments
        WHERE debt_id = ?
        ORDER BY payment_date DESC, id DESC
        """,
        (debt_id,),
    ).fetchall()
    return [_row_to_payment(r) for r in rows]
