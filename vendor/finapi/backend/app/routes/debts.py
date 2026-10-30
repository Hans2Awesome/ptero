"""Debt and receivable management routes."""

from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from finance_core.db.debts import (
    create_debt,
    create_debt_payment,
    delete_debt,
    get_debt_by_id,
    get_debt_summary,
    list_debt_payments,
    list_debts,
    update_debt,
)
from finance_core.db.users import AppUser
from finance_core.timezones import today_in

from ..auth.dependencies import get_current_user, get_db
from ..models.schemas import (
    DebtCreate,
    DebtPaymentCreate,
    DebtPaymentResponse,
    DebtResponse,
    DebtSummaryResponse,
    DebtUpdate,
)

router = APIRouter(prefix="/api/debts", tags=["Debts & Receivables"])

NOT_FOUND_DETAIL = "Hutang/piutang tidak ditemukan."


@router.post("", response_model=DebtResponse, status_code=status.HTTP_201_CREATED)
def create_new_debt(
    payload: DebtCreate,
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> DebtResponse:
    """Create a new debt or receivable record."""

    debt = create_debt(
        db,
        user_id=current_user.id,
        type=payload.type,
        person_name=payload.person_name,
        total_amount=payload.total_amount,
        note=payload.note,
        due_date=payload.due_date.isoformat() if payload.due_date else None,
    )
    return DebtResponse.model_validate(debt)


@router.get("/summary", response_model=DebtSummaryResponse)
def get_summary(
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> DebtSummaryResponse:
    """Get an aggregated summary of debts and receivables."""

    summary = get_debt_summary(
        db,
        user_id=current_user.id,
        today=today_in(current_user.timezone).isoformat(),
    )
    return DebtSummaryResponse(**summary)


@router.get("", response_model=list[DebtResponse])
def get_debts(
    type: Optional[str] = Query(None, pattern="^(debt|receivable)$"),
    status_filter: Optional[str] = Query(None, alias="status", pattern="^(active|settled)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> list[DebtResponse]:
    """List debts/receivables with optional filters."""

    items = list_debts(
        db,
        user_id=current_user.id,
        debt_type=type,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return [DebtResponse.model_validate(item) for item in items]


@router.get("/{debt_id}", response_model=DebtResponse)
def get_debt(
    debt_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> DebtResponse:
    """Get a single debt/receivable by ID."""

    debt = get_debt_by_id(db, user_id=current_user.id, debt_id=debt_id)
    if debt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return DebtResponse.model_validate(debt)


@router.put("/{debt_id}", response_model=DebtResponse)
def edit_debt(
    debt_id: int,
    payload: DebtUpdate,
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> DebtResponse:
    """Update fields of an existing debt/receivable."""

    try:
        updated = update_debt(
            db,
            user_id=current_user.id,
            debt_id=debt_id,
            person_name=payload.person_name,
            total_amount=payload.total_amount,
            note=payload.note,
            due_date=payload.due_date.isoformat() if payload.due_date else None,
            status=payload.status,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return DebtResponse.model_validate(updated)


@router.delete("/{debt_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_debt(
    debt_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    """Delete a debt/receivable and all its payments."""

    if not delete_debt(db, user_id=current_user.id, debt_id=debt_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)


@router.post(
    "/{debt_id}/payments",
    response_model=DebtPaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_payment(
    debt_id: int,
    payload: DebtPaymentCreate,
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> DebtPaymentResponse:
    """Record a payment/installment for a debt or receivable."""

    try:
        payment = create_debt_payment(
            db,
            debt_id=debt_id,
            user_id=current_user.id,
            amount=payload.amount,
            note=payload.note,
            payment_date=payload.payment_date.isoformat(),
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pembayaran tidak dapat disimpan.",
        ) from error

    return DebtPaymentResponse.model_validate(payment)


@router.get("/{debt_id}/payments", response_model=list[DebtPaymentResponse])
def get_payments(
    debt_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> list[DebtPaymentResponse]:
    """List all payments for one debt/receivable."""

    payments = list_debt_payments(db, debt_id=debt_id, user_id=current_user.id)
    return [DebtPaymentResponse.model_validate(payment) for payment in payments]