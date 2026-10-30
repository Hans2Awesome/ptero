"""Category management routes."""

from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from finance_core.db.categories import create_category, delete_category, list_categories
from finance_core.db.users import AppUser

from ..auth.dependencies import get_current_user, get_db
from ..models.schemas import CategoryCreate, CategoryResponse

router = APIRouter(prefix="/api/categories", tags=["Categories"])


@router.get("", response_model=list[CategoryResponse])
def get_categories(
    type: Optional[str] = None,
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> list[CategoryResponse]:
    """List all categories for the current user, optionally filtered by type."""

    categories = list_categories(db, current_user.id, category_type=type)
    return [CategoryResponse.model_validate(category) for category in categories]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def add_category(
    payload: CategoryCreate,
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> CategoryResponse:
    """Create a new custom category."""

    try:
        created = create_category(
            db,
            user_id=current_user.id,
            type=payload.type,
            name=payload.name,
            aliases=payload.aliases,
        )
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kategori dengan nama dan tipe tersebut sudah ada.",
        ) from error

    return CategoryResponse.model_validate(created)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_category(
    category_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    """Delete a custom category."""

    if not delete_category(db, user_id=current_user.id, category_id=category_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kategori tidak ditemukan.",
        )