"""Django-owned financial series, independent of any chart renderer."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import QuerySet

from .allocations import NON_EXPENSE_CATEGORY_TYPES, iter_expense_allocations
from .expense_list import month_key, shift_month
from .models import Category, Expense

ZERO = Decimal("0.00")


def _expenses(user: User) -> QuerySet[Expense]:
    return (
        Expense.objects.filter(user=user)
        .select_related(
            "category_obj",
            "category_obj__parent",
            "category_obj__parent__parent",
            "category_obj__parent__parent__parent",
            "category_obj__parent__parent__parent__parent",
        )
        .order_by("date", "pk")
    )


def _owned_root(category: Category | None, user_id: int) -> Category | None:
    seen = set()
    while category is not None:
        if category.user_id != user_id or category.pk in seen:
            return None
        if category.parent_id is None:
            return category
        seen.add(category.pk)
        category = category.parent
    return None


def _spending_points(spending: dict[date, Decimal]) -> list[dict]:
    cumulative = ZERO
    daily = []
    for day, amount in sorted(spending.items()):
        cumulative += amount
        daily.append({"date": day, "daily": abs(amount), "cumulative": abs(cumulative)})
    return daily


def _cash_flow_points(spending: dict[date, Decimal], income: dict[date, Decimal]) -> list[dict]:
    spent, earned = ZERO, ZERO
    points = []
    for day in sorted(spending.keys() | income.keys()):
        spent += spending.get(day, ZERO)
        earned += income.get(day, ZERO)
        points.append({"date": day, "income": earned, "expenses": abs(spent), "balance": earned + spent})
    return points


def _category_breakdown(totals: dict[str, Decimal], month: date, current: date) -> dict:
    magnitudes = sorted(
        ((name, abs(amount)) for name, amount in totals.items()),
        key=lambda item: item[1],
        reverse=True,
    )
    total = sum((amount for _, amount in magnitudes), ZERO)
    return {
        "month": month_key(month),
        "label": month.strftime("%B %Y"),
        "previous": month_key(shift_month(month, -1)) if month > date.min else None,
        "next": month_key(shift_month(month, 1)) if month not in (current, date(9999, 12, 1)) else None,
        "total": total,
        "rows": [
            {
                "name": name,
                "amount": amount,
                "percent": (amount * 100 / total).quantize(ZERO) if total else ZERO,
            }
            for name, amount in magnitudes
        ],
    }


def read_analytics(user: User, month_param: str) -> dict:
    current = date.today().replace(day=1)
    try:
        month = date.fromisoformat(month_param + "-01")
    except ValueError:
        month = current  # Keep legacy deep links with invalid months working.

    spending: dict[date, Decimal] = defaultdict(lambda: ZERO)
    income: dict[date, Decimal] = defaultdict(lambda: ZERO)
    category_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for allocation in iter_expense_allocations(_expenses(user).iterator()):
        category = allocation.category
        root = _owned_root(category, user.pk)
        kind = (
            category.category_type
            if category is not None and root is not None
            else Category.CATEGORY_TYPE_EXPENSE
        )
        day = allocation.expense.date
        if kind == Category.CATEGORY_TYPE_INCOME:
            income[day] += allocation.amount
        if kind in NON_EXPENSE_CATEGORY_TYPES:
            continue
        spending[day] += allocation.amount
        if day.year == month.year and day.month == month.month:
            name = root.name if root is not None else "Uncategorized"
            category_totals[name] += allocation.amount

    # Accumulate signed values before taking magnitudes, so refunds offset spending.
    monthly: dict[date, Decimal] = defaultdict(lambda: ZERO)
    yearly: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for day, amount in spending.items():
        monthly[day.replace(day=1)] += amount
        yearly[day.year] += amount

    return {
        "daily": _spending_points(spending),
        "monthly": [
            {"month": month_key(period), "total_spent": abs(amount)}
            for period, amount in sorted(monthly.items())
        ],
        "category": _category_breakdown(category_totals, month, current),
        "cash_flow": _cash_flow_points(spending, income),
        "yearly": [
            {"year": year, "total_spent": abs(amount)} for year, amount in sorted(yearly.items())
        ],
    }
