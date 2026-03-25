from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from .models import Category, Expense

NON_EXPENSE_CATEGORY_TYPES = (
    Category.CATEGORY_TYPE_SAVING,
    Category.CATEGORY_TYPE_TRANSFER,
    Category.CATEGORY_TYPE_INCOME,
)
TWOPLACES = Decimal("0.01")


@dataclass(frozen=True)
class ExpenseAllocation:
    expense: Expense
    category: Category | None
    amount: Decimal


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def get_expense_allocations(expense: Expense) -> list[ExpenseAllocation]:
    user_amount = expense.get_effective_user_amount()
    source_amount = expense.get_source_amount()
    source_total = abs(source_amount)

    if source_total == 0:
        return []

    prefetched_parts = getattr(expense, "_prefetched_objects_cache", {}).get("parts")
    parts = list(prefetched_parts) if prefetched_parts is not None else list(expense.parts.all())

    if not parts:
        return [ExpenseAllocation(expense=expense, category=expense.category_obj, amount=user_amount)]

    components: list[tuple[Category | None, Decimal]] = [
        (part.category_obj, part.amount) for part in parts
    ]
    remainder = expense.get_remainder_amount()
    if remainder > 0:
        components.append((expense.category_obj, remainder))

    if not components:
        return []

    allocations: list[ExpenseAllocation] = []
    allocated_total = Decimal("0")
    sign = Decimal("1") if user_amount >= 0 else Decimal("-1")
    ratio = abs(user_amount) / source_total

    for index, (category, component_amount) in enumerate(components):
        if index == len(components) - 1:
            allocation_amount = user_amount - allocated_total
        else:
            allocation_amount = sign * _quantize(component_amount * ratio)
            allocated_total += allocation_amount
        allocations.append(
            ExpenseAllocation(
                expense=expense,
                category=category,
                amount=allocation_amount,
            )
        )

    return allocations


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
