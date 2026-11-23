from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from heapq import nsmallest

from django.contrib.auth.models import User
from django.db.models import FilteredRelation, Q

from .allocations import (
    NON_EXPENSE_CATEGORY_TYPES,
    ExpenseAllocation,
    iter_expense_allocations,
    summarize_allocations,
)
from .forms import UNCATEGORIZED_SENTINEL, SortForm
from .models import Category, Expense

SORT_FIELDS = {"date", "amount", "category_obj__name", "receiver"}


def shift_month(value: date, months: int) -> date:
    """Return the first of the shifted month."""
    year_offset, month_index = divmod(value.month - 1 + months, 12)
    return date(value.year + year_offset, month_index + 1, 1)


def month_key(value: date) -> str:
    return value.isoformat()[:7]


@dataclass(frozen=True)
class ExpenseFilters:
    month: date
    current_month: date
    is_all: bool
    order_by: str
    category_filter: str
    search: str

    @classmethod
    def from_params(cls, params: Mapping[str, str], form: SortForm) -> "ExpenseFilters":
        current_month = date.today().replace(day=1)
        month = current_month
        month_param = params.get("month", "")
        is_all = month_param == "all"
        if month_param and not is_all:
            try:
                month = date.fromisoformat(month_param + "-01")
            except ValueError:
                pass  # Retain the legacy current-month fallback.

        order_by = params.get("order_by", "")
        if order_by.removeprefix("-") not in SORT_FIELDS:
            order_by = "-date"

        cleaned = form.cleaned_data if form.is_valid() else {}
        return cls(
            month,
            current_month,
            is_all,
            order_by,
            cleaned.get("category_filter", ""),
            cleaned.get("search", ""),
        )

    @property
    def period(self) -> str:
        return "all" if self.is_all else month_key(self.month)

    @property
    def previous(self) -> str | None:
        if self.month != date.min:
            return month_key(shift_month(self.month, -1))
        return None

    @property
    def next(self) -> str | None:
        if (
            not self.is_all
            and self.month != self.current_month
            and self.month != date(9999, 12, 1)
        ):
            return month_key(shift_month(self.month, 1))
        return None


def picker_years(user: User, current_month: date) -> range:
    earliest = (
        Expense.objects.filter(user=user)
        .order_by("date")
        .values_list("date", flat=True)
        .first()
    )
    first_year = (
        min(earliest.year, current_month.year) if earliest else current_month.year
    )
    return range(first_year, current_month.year + 1)


@dataclass(frozen=True)
class ExpenseListRow:
    allocation: ExpenseAllocation

    @property
    def expense(self) -> Expense:
        return self.allocation.expense

    @property
    def category(self) -> Category | None:
        return self.allocation.category

    @property
    def category_name(self) -> str:
        return self.category.name if self.category else "Uncategorized"

    @property
    def amount(self) -> Decimal:
        return self.allocation.amount


def _descendant_ids(root_id: int, categories: Iterable[Category]) -> set[int]:
    children = defaultdict(list)
    for category in categories:
        children[category.parent_id].append(category.pk)
    pending = [root_id]
    visited = {root_id}
    while pending:
        for child in children[pending.pop()]:
            if child not in visited:
                visited.add(child)
                pending.append(child)
    return visited


@dataclass(frozen=True)
class ExpenseList:
    rows: list[ExpenseListRow]

    def summary(self) -> dict[str, Decimal]:
        return summarize_allocations(row.allocation for row in self.rows)

    def top_expenses(self) -> list[ExpenseListRow]:
        return nsmallest(
            5,
            (
                row
                for row in self.rows
                if row.amount < 0
                and (
                    row.category is None
                    or row.category.category_type not in NON_EXPENSE_CATEGORY_TYPES
                )
            ),
            key=lambda row: row.amount,
        )


def read_expense_list(
    user: User, filters: ExpenseFilters, categories: list[Category]
) -> ExpenseList:
    """A visible row represents one nonzero source expense."""
    queryset = (
        Expense.objects.filter(user=user)
        .exclude(amount=0)
        .select_related("category_obj", "split_rule")
    )
    order_by = filters.order_by
    if filters.search or order_by.removeprefix("-") == "category_obj__name":
        queryset = queryset.alias(
            owned_category=FilteredRelation(
                "category_obj", condition=Q(category_obj__user=user)
            )
        )
        order_by = order_by.replace("category_obj__name", "owned_category__name")
    queryset = queryset.order_by(order_by, "pk")
    if not filters.is_all:
        queryset = queryset.filter(
            date__year=filters.month.year, date__month=filters.month.month
        )
    if filters.search:
        queryset = queryset.filter(
            Q(receiver__icontains=filters.search)
            | Q(description__icontains=filters.search)
            | Q(category__icontains=filters.search)
            | Q(owned_category__name__icontains=filters.search)
        )

    owned_categories = {str(category.pk): category for category in categories}
    selected = owned_categories.get(filters.category_filter)
    if selected:
        category_ids = _descendant_ids(selected.pk, categories)
        queryset = queryset.filter(category_obj_id__in=category_ids)
    elif filters.category_filter == UNCATEGORIZED_SENTINEL:
        queryset = queryset.exclude(category_obj__user=user)

    rows = []
    search = filters.search.lower()
    for allocation in iter_expense_allocations(queryset.iterator(chunk_size=500)):
        expense = allocation.expense
        if allocation.category and allocation.category.user_id != user.pk:
            allocation = replace(allocation, category=None)
        row = ExpenseListRow(allocation)
        # Keep legacy's case-insensitive SQL search followed by its row-level check.
        if search and not any(
            search in value.lower()
            for value in (
                expense.receiver,
                expense.description,
                expense.category,
                row.category_name,
            )
        ):
            continue
        rows.append(row)
    return ExpenseList(rows)
