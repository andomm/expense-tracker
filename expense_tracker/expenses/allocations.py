from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from .models import Category, Expense

NON_EXPENSE_CATEGORY_TYPES = (
    Category.CATEGORY_TYPE_SAVING,
    Category.CATEGORY_TYPE_TRANSFER,
    Category.CATEGORY_TYPE_INCOME,
)


@dataclass(frozen=True)
class ExpenseAllocation:
    expense: Expense
    category: Category | None
    amount: Decimal


def get_expense_allocations(expense: Expense) -> list[ExpenseAllocation]:
    source_amount = expense.get_source_amount()

    if abs(source_amount) == 0:
        return []

    user_amount = expense.get_effective_user_amount()
    return [ExpenseAllocation(expense=expense, category=expense.category_obj, amount=user_amount)]


def iter_expense_allocations(expenses: Iterable[Expense]):
    for expense in expenses:
        yield from get_expense_allocations(expense)


def expense_matches_category_ids(expense: Expense, category_ids: set[int]) -> bool:
    return any(
        allocation.category and allocation.category.pk in category_ids
        for allocation in get_expense_allocations(expense)
    )


def is_uncategorized_expense(expense: Expense) -> bool:
    return any(
        allocation.category is None for allocation in get_expense_allocations(expense)
    )


def summarize_allocations(
    allocations: Iterable[ExpenseAllocation],
) -> dict[str, Decimal]:
    totals = {
        "total_spent": Decimal("0"),
        "income": Decimal("0"),
        "savings_total": Decimal("0"),
    }

    for allocation in allocations:
        category_type = (
            allocation.category.category_type
            if allocation.category
            else Category.CATEGORY_TYPE_EXPENSE
        )

        if category_type == Category.CATEGORY_TYPE_INCOME:
            totals["income"] += allocation.amount
            continue

        if category_type == Category.CATEGORY_TYPE_SAVING:
            totals["savings_total"] += abs(allocation.amount)
            continue

        if (
            allocation.amount < 0
            and category_type not in NON_EXPENSE_CATEGORY_TYPES
        ):
            totals["total_spent"] += allocation.amount

    totals["balance"] = totals["total_spent"] + totals["income"]
    return totals


def summarize_expenses(expenses: Iterable[Expense]) -> dict[str, Decimal]:
    return summarize_allocations(iter_expense_allocations(expenses))


def build_monthly_spending_summary(expenses: Iterable[Expense]) -> list[dict]:
    monthly_totals: dict = defaultdict(lambda: Decimal("0"))

    for allocation in iter_expense_allocations(expenses):
        category_type = (
            allocation.category.category_type
            if allocation.category
            else Category.CATEGORY_TYPE_EXPENSE
        )
        if allocation.amount >= 0 or category_type in NON_EXPENSE_CATEGORY_TYPES:
            continue
        month = allocation.expense.date.replace(day=1)
        monthly_totals[month] += abs(allocation.amount)

    return [
        {"month": month, "total_spent": total}
        for month, total in sorted(monthly_totals.items())
    ]
