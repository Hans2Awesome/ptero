"""Pydantic schemas for request validation and response serialization."""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

TransactionTypeValue = Literal["income", "expense", "investment"]
DebtTypeValue = Literal["debt", "receivable"]
DebtStatusValue = Literal["active", "settled"]


# --- Auth Schemas ---


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: Optional[str] = Field(None, max_length=80)
    timezone: str = "Asia/Jakarta"
    currency: str = Field("IDR", min_length=3, max_length=3)

    @field_validator("password")
    @classmethod
    def _password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Kata sandi maksimal 72 byte.")
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: Optional[str] = None
    first_name: Optional[str] = None
    timezone: str = "Asia/Jakarta"
    currency: str = "IDR"
    created_at: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


# --- Category Schemas ---


class CategoryCreate(BaseModel):
    type: TransactionTypeValue
    name: str = Field(..., min_length=1, max_length=80)
    aliases: str = ""


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    type: str
    name: str
    aliases: str = ""
    is_default: int = 0


# --- Transaction Schemas ---


class TransactionCreate(BaseModel):
    type: TransactionTypeValue
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    amount: int = Field(..., gt=0)
    note: Optional[str] = Field(None, max_length=500)
    asset_name: Optional[str] = Field(None, max_length=80)
    transaction_date: date


class TransactionUpdate(BaseModel):
    amount: Optional[int] = Field(None, gt=0)
    category_id: Optional[int] = None
    transaction_date: Optional[date] = None
    note: Optional[str] = Field(None, max_length=500)
    asset_name: Optional[str] = Field(None, max_length=80)


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    type: str
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    amount: int
    note: Optional[str] = None
    asset_name: Optional[str] = None
    transaction_date: str


class QuickInputRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=200)
    reference_date: Optional[date] = None


class QuickInputPreviewResponse(BaseModel):
    type: Optional[str] = None
    type_label: Optional[str] = None
    category_name: Optional[str] = None
    amount: Optional[int] = None
    note: Optional[str] = None
    asset_name: Optional[str] = None
    transaction_date: Optional[str] = None
    is_valid: bool
    error: Optional[str] = None


# --- Report Schemas ---


class CategoryTotalItem(BaseModel):
    name: str
    amount: int
    percentage: float = 0.0


class PeriodReportResponse(BaseModel):
    title: str
    start_date: str
    end_date: str
    total_income: int
    total_expense: int
    total_investment: int
    net: int
    average_expense: int
    investment_percentage: float
    top_expense_categories: list[CategoryTotalItem]


class CategoryBreakdownResponse(BaseModel):
    title: str
    type: str
    categories: list[CategoryTotalItem]
    total_amount: int


class InvestmentReportResponse(BaseModel):
    title: str
    total_investment: int
    investment_percentage: float
    by_type: list[CategoryTotalItem]
    by_asset: list[CategoryTotalItem]


# --- Debt Schemas ---


class DebtCreate(BaseModel):
    type: DebtTypeValue
    person_name: str = Field(..., min_length=1, max_length=120)
    total_amount: int = Field(..., gt=0)
    note: Optional[str] = Field(None, max_length=500)
    due_date: Optional[date] = None


class DebtUpdate(BaseModel):
    person_name: Optional[str] = Field(None, min_length=1, max_length=120)
    total_amount: Optional[int] = Field(None, gt=0)
    note: Optional[str] = Field(None, max_length=500)
    due_date: Optional[date] = None
    status: Optional[DebtStatusValue] = None


class DebtResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    type: str
    person_name: str
    total_amount: int
    paid_amount: int
    note: Optional[str] = None
    due_date: Optional[str] = None
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DebtPaymentCreate(BaseModel):
    amount: int = Field(..., gt=0)
    note: Optional[str] = Field(None, max_length=500)
    payment_date: date


class DebtPaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    debt_id: int
    amount: int
    note: Optional[str] = None
    payment_date: str
    created_at: Optional[str] = None


class DebtSummaryResponse(BaseModel):
    total_debt_remaining: int
    total_receivable_remaining: int
    active_debt_count: int
    active_receivable_count: int
    due_soon_count: int