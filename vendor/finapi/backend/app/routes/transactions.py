"""Transaction management routes."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from finance_core.db.categories import category_belongs_to
from finance_core.db.transactions import (
    create_transaction,
    delete_transaction,
    get_transaction_by_id,
    list_transactions,
    update_transaction,
)
from finance_core.db.users import AppUser
from finance_core.domain import transaction_type_label
from finance_core.services.quick_input_parser import parse_quick_input
from finance_core.services.transaction_service import (
    TransactionServiceError,
    find_or_create_category,
    save_quick_input_transaction,
)

from ..auth.dependencies import get_current_user, get_db
from ..models.schemas import (
    QuickInputPreviewResponse,
    QuickInputRequest,
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])

NOT_FOUND_DETAIL = "Transaksi tidak ditemukan."


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_new_transaction(
    payload: TransactionCreate,
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> TransactionResponse:
    """Create a new transaction manually."""

    category_id = payload.category_id
    if category_id is not None and not category_belongs_to(
        db,
        user_id=current_user.id,
        category_id=category_id,
        category_type=payload.type,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kategori tidak valid untuk transaksi ini.",
        )
    if category_id is None and payload.category_name:
        category_id = find_or_create_category(
            db,
            user_id=current_user.id,
            category_type=payload.type,
            category_name=payload.category_name,
        )

    transaction = create_transaction(
        db,
        user_id=current_user.id,
        type=payload.type,
        category_id=category_id,
        amount=payload.amount,
        note=payload.note,
        asset_name=payload.asset_name,
        transaction_date=payload.transaction_date.isoformat(),
    )
    return TransactionResponse.model_validate(transaction)


@router.post("/quick-input", response_model=QuickInputPreviewResponse)
def preview_quick_input(
    payload: QuickInputRequest,
    current_user: AppUser = Depends(get_current_user),
) -> QuickInputPreviewResponse:
    """Parse quick input text and return a preview before saving."""

    result = parse_quick_input(
        payload.text,
        today=payload.reference_date,
        timezone=current_user.timezone,
    )

    if result.error:
        return QuickInputPreviewResponse(
            note=result.note,
            is_valid=False,
            error=result.error,
        )

    return QuickInputPreviewResponse(
        type=result.type,
        type_label=transaction_type_label(result.type) if result.type else None,
        category_name=result.category_name,
        amount=result.amount,
        note=result.note,
        asset_name=result.asset_name,
        transaction_date=result.transaction_date.isoformat() if result.transaction_date else None,
        is_valid=True,
        error=None,
    )


@router.post(
    "/quick-input/confirm",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def confirm_quick_input(
    payload: QuickInputRequest,
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> TransactionResponse:
    """Parse and immediately save quick input."""

    result = parse_quick_input(
        payload.text,
        today=payload.reference_date,
        timezone=current_user.timezone,
    )
    if result.error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error,
        )

    try:
        transaction = save_quick_input_transaction(db, user_id=current_user.id, preview=result)
    except TransactionServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    return TransactionResponse.model_validate(transaction)


@router.get("", response_model=list[TransactionResponse])
def get_transactions(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    type: Optional[str] = Query(None, description="Transaction type filter"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> list[TransactionResponse]:
    """List transactions with optional filters and pagination."""

    items = list_transactions(
        db,
        user_id=current_user.id,
        start_date=start_date.isoformat() if start_date else None,
        end_date=end_date.isoformat() if end_date else None,
        transaction_type=type,
        limit=limit,
        offset=offset,
    )
    return [TransactionResponse.model_validate(item) for item in items]


@router.get("/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> TransactionResponse:
    """Get a single transaction by ID."""

    transaction = get_transaction_by_id(
        db,
        user_id=current_user.id,
        transaction_id=transaction_id,
    )
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return TransactionResponse.model_validate(transaction)


@router.put("/{transaction_id}", response_model=TransactionResponse)
def edit_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> TransactionResponse:
    """Update fields of an existing transaction."""

    if payload.category_id is not None:
        existing = get_transaction_by_id(
            db,
            user_id=current_user.id,
            transaction_id=transaction_id,
        )
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
        if not category_belongs_to(
            db,
            user_id=current_user.id,
            category_id=payload.category_id,
            category_type=existing.type,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kategori tidak valid untuk transaksi ini.",
            )

    updated = update_transaction(
        db,
        user_id=current_user.id,
        transaction_id=transaction_id,
        amount=payload.amount,
        category_id=payload.category_id,
        transaction_date=(
            payload.transaction_date.isoformat() if payload.transaction_date else None
        ),
        note=payload.note,
        asset_name=payload.asset_name,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return TransactionResponse.model_validate(updated)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_transaction(
    transaction_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    """Delete a transaction."""

    if not delete_transaction(db, user_id=current_user.id, transaction_id=transaction_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)