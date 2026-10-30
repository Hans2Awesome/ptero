"""Aggregate transaction data for reports and visualization."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..db.transactions import Transaction


@dataclass(frozen=True)
class CategoryTotal:
    """Total amount and percentage for one category."""

    name: str
    amount: int
    percentage: float = 0.0


@dataclass(frozen=True)
class ReportSummary:
    """Aggregated financial summary for a transaction list."""

    total_income: int
    total_expense: int
    total_investment: int
    net: int
    average_expense: int
    top_expense_categories: list[CategoryTotal]
    investment_percentage: float


def aggregate_transactions(
    transactions: list[Transaction],
    *,
    category_names: dict[int, str] | None = None,
) -> ReportSummary:
    """Aggregate totals, net, expense categories, and investment percentage."""
    names = category_names or {}
    total_income = 0
    total_expense = 0
    total_investment = 0
    expense_count = 0
    expense_totals_by_category: dict[str, int] = defaultdict(int)

    for transaction in transactions:
        if transaction.type == "income":
            total_income += transaction.amount
        elif transaction.type == "expense":
            total_expense += transaction.amount
            expense_count += 1
            category_name = (
                transaction.category_name
                or names.get(transaction.category_id or 0, "Lainnya")
            )
            expense_totals_by_category[category_name] += transaction.amount
        elif transaction.type == "investment":
            total_investment += transaction.amount

    net = total_income - total_expense - total_investment
    average_expense = total_expense // expense_count if expense_count else 0
    investment_percentage = (
        round((total_investment / total_income) * 100, 2) if total_income > 0 else 0.0
    )

    top_expense_categories = [
        CategoryTotal(
            name=name,
            amount=amount,
            percentage=round((amount / total_expense * 100), 1) if total_expense > 0 else 0.0,
        )
        for name, amount in sorted(
            expense_totals_by_category.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

    return ReportSummary(
        total_income=total_income,
        total_expense=total_expense,
        total_investment=total_investment,
        net=net,
        average_expense=average_expense,
        top_expense_categories=top_expense_categories,
        investment_percentage=investment_percentage,
    )


def aggregate_by_category(
    transactions: list[Transaction],
    category_type: str,
    *,
    category_names: dict[int, str] | None = None,
) -> tuple[list[CategoryTotal], int]:
    """Aggregate transactions of a specific type by category with percentages."""
    names = category_names or {}
    totals: dict[str, int] = defaultdict(int)
    total_amount = 0

    for tx in transactions:
        if tx.type == category_type:
            total_amount += tx.amount
            name = tx.category_name or names.get(tx.category_id or 0, "Lainnya")
            totals[name] += tx.amount

    items = [
        CategoryTotal(
            name=name,
            amount=amt,
            percentage=round((amt / total_amount * 100), 1) if total_amount > 0 else 0.0,
        )
        for name, amt in sorted(totals.items(), key=lambda x: -x[1])
    ]
    return items, total_amount


def aggregate_investments(
    transactions: list[Transaction],
    *,
    category_names: dict[int, str] | None = None,
) -> tuple[list[CategoryTotal], list[CategoryTotal], int]:
    """Aggregate investments by type and by asset name."""
    names = category_names or {}
    type_totals: dict[str, int] = defaultdict(int)
    asset_totals: dict[str, int] = defaultdict(int)
    total_invested = 0

    for tx in transactions:
        if tx.type == "investment":
            total_invested += tx.amount
            type_name = tx.category_name or names.get(tx.category_id or 0, "Lainnya")
            type_totals[type_name] += tx.amount
            asset = tx.asset_name or type_name
            asset_totals[asset] += tx.amount

    by_type = [
        CategoryTotal(
            name=name,
            amount=amt,
            percentage=round((amt / total_invested * 100), 1) if total_invested > 0 else 0.0,
        )
        for name, amt in sorted(type_totals.items(), key=lambda x: -x[1])
    ]

    by_asset = [
        CategoryTotal(
            name=name,
            amount=amt,
            percentage=round((amt / total_invested * 100), 1) if total_invested > 0 else 0.0,
        )
        for name, amt in sorted(asset_totals.items(), key=lambda x: -x[1])
    ]

    return by_type, by_asset, total_invested
