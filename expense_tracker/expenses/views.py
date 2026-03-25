from datetime import date
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from itertools import groupby
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db import models
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .importers import get_importer

from .allocations import (
    ExpenseAllocation,
    build_monthly_spending_summary,
    expense_matches_category_ids,
    get_expense_allocations,
    is_uncategorized_expense,
    summarize_allocations,
)
from .helpers import categorize_from_sources

from .forms import (
    BulkCategoryUpdateForm,
    CSVUploadForm,
    CategoryForm,
    ExpenseForm,
    ExpensePartFormSet,
    SortForm,
    UNCATEGORIZED_SENTINEL,
)

from .models import Expense, Category

from expenses.charts import (
    create_category_breakdown,
    create_cumulative_graph,
    create_income_vs_expenses,
    create_monthly_comparison,
)

PREVIEW_LIMIT = 50

NON_EXPENSE_CATEGORY_TYPES = (
    Category.CATEGORY_TYPE_SAVING,
    Category.CATEGORY_TYPE_TRANSFER,
    Category.CATEGORY_TYPE_INCOME,
)


@dataclass(frozen=True)
class ExpenseListRow:
    allocation: ExpenseAllocation
    group_size: int = 1
    show_parent_cells: bool = True
    split_component_label: str | None = None

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

    @property
    def is_split_expense(self) -> bool:
        return self.expense.has_split_parts()


@login_required
def expenses_per_month(request):
    today = date.today()
    month_param = request.GET.get("month", "")
    active_month_date = today.replace(day=1)

    if month_param:
        try:
            active_month_date = date.fromisoformat(month_param + "-01")
        except ValueError:
            pass

    prev_month_str = _add_months(active_month_date, -1).strftime("%Y-%m")
    next_month_date = _add_months(active_month_date, 1)
    next_month_str = next_month_date.strftime("%Y-%m")
    is_current_month = (
        active_month_date.year == today.year and active_month_date.month == today.month
    )
    active_month_label = active_month_date.strftime("%B %Y")

    monthly_totals = build_monthly_spending_summary(
        Expense.objects.filter(user=request.user)
        .select_related(
            "category_obj",
            "category_obj__parent",
            "category_obj__parent__parent",
            "category_obj__parent__parent__parent",
            "category_obj__parent__parent__parent__parent",
        )
        .prefetch_related(
            "parts__category_obj",
            "parts__category_obj__parent",
            "parts__category_obj__parent__parent",
            "parts__category_obj__parent__parent__parent",
            "parts__category_obj__parent__parent__parent__parent",
        )
    )

    cumulative_graph = create_cumulative_graph(request.user)
    monthly_comparison = create_monthly_comparison(request.user)
    category_breakdown = create_category_breakdown(
        request.user,
        active_month_date=active_month_date,
    )
    income_vs_expenses = create_income_vs_expenses(request.user)

    return render(
        request,
        "expenses/expenses_per_month.html",
        {
            "expenses_per_month": monthly_totals,
            "cumulative_graph": cumulative_graph,
            "monthly_comparison": monthly_comparison,
            "category_breakdown": category_breakdown,
            "income_vs_expenses": income_vs_expenses,
            "active_month_label": active_month_label,
            "active_month_str": active_month_date.strftime("%Y-%m"),
            "prev_month_str": prev_month_str,
            "next_month_str": next_month_str,
            "is_current_month": is_current_month,
        },
    )


def _add_months(d, months):
    """Return a date shifted by `months` from d."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, 1)


def _build_expense_list_url(params):
    query_params = {}

    for key in ("month", "order_by", "category_filter", "search"):
        value = params.get(key)
        if value:
            query_params[key] = value

    base_url = reverse("expense_list")
    if not query_params:
        return base_url
    return f"{base_url}?{urlencode(query_params)}"


def _build_expense_list_query_string(params):
    return urlencode(
        {
            key: value
            for key in ("month", "order_by", "category_filter", "search")
            if (value := params.get(key))
        }
    )


def _get_bulk_category_error_message(request, form):
    if "expense_ids" in form.errors:
        if request.POST.getlist("expense_ids"):
            return "One or more selected expenses are invalid."
        return "Select at least one expense to update."

    if "category_obj" in form.errors:
        if request.POST.get("category_obj"):
            return "Select a valid category."
        return "Select a category."

    return "Could not update the selected expenses."


def _parse_decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _get_expense_form_context(request, *, return_url=None):
    return {
        "return_url": return_url,
        "return_month": request.GET.get("month", request.POST.get("month", "")),
        "return_order_by": request.GET.get("order_by", request.POST.get("order_by", "")),
        "return_category_filter": request.GET.get(
            "category_filter", request.POST.get("category_filter", "")
        ),
        "return_search": request.GET.get("search", request.POST.get("search", "")),
    }


def _build_expense_part_formset(*, request, expense, user, total_amount):
    if request.method == "POST":
        return ExpensePartFormSet(
            request.POST,
            instance=expense,
            user=user,
            total_amount=total_amount,
        )
    return ExpensePartFormSet(
        instance=expense,
        user=user,
        total_amount=total_amount,
    )


def _save_expense_parts(formset, expense):
    for deleted_form in formset.deleted_forms:
        if deleted_form.instance.pk:
            deleted_form.instance.delete()

    order = 0
    for part_form in formset.forms:
        if not getattr(part_form, "cleaned_data", None):
            continue
        if part_form.cleaned_data.get("DELETE"):
            continue

        amount = part_form.cleaned_data.get("amount")
        category = part_form.cleaned_data.get("category_obj")
        if amount is None or category is None:
            continue

        part = part_form.save(commit=False)
        part.expense = expense
        part.order = order
        part.save()
        order += 1


def _validate_split_remainder(form, formset):
    split_total = Decimal("0")
    for part_form in formset.forms:
        if not getattr(part_form, "cleaned_data", None):
            continue
        if part_form.cleaned_data.get("DELETE"):
            continue
        amount = part_form.cleaned_data.get("amount")
        if amount:
            split_total += amount

    if split_total >= abs(form.cleaned_data["amount"]):
        return

    if form.cleaned_data.get("category_obj"):
        return

    form.add_error(
        "category_obj",
        "Select a category for the remaining amount or split the full expense.",
    )


def _build_split_summary(form, formset):
    if not form.is_bound and not form.instance.pk:
        return None

    amount = None
    if getattr(form, "cleaned_data", None):
        amount = form.cleaned_data.get("amount")
    if amount is None:
        amount = form.initial.get("amount", form.instance.amount)

    amount = _parse_decimal(amount)
    if amount is None:
        return None

    split_total = Decimal("0")
    for part_form in formset.forms:
        cleaned_data = getattr(part_form, "cleaned_data", None)
        if cleaned_data:
            if cleaned_data.get("DELETE"):
                continue
            part_amount = cleaned_data.get("amount")
            if part_amount:
                split_total += part_amount
            continue

        initial_amount = _parse_decimal(part_form.initial.get("amount"))
        if initial_amount:
            split_total += initial_amount

    remainder = abs(amount) - split_total
    if remainder < 0:
        remainder = Decimal("0")

    category = None
    if getattr(form, "cleaned_data", None):
        category = form.cleaned_data.get("category_obj")
    if category is None:
        category = form.initial.get("category_obj", form.instance.category_obj)

    return {
        "split_total": split_total,
        "remainder": remainder,
        "remainder_category_name": category.name if category else "Uncategorized",
    }


def _build_expense_rows(expenses):
    rows: list[ExpenseListRow] = []

    for expense in expenses:
        allocations = get_expense_allocations(expense)
        if not allocations:
            continue

        if not expense.has_split_parts():
            rows.append(ExpenseListRow(allocation=allocations[0]))
            continue

        prefetched_parts = getattr(expense, "_prefetched_objects_cache", {}).get("parts")
        part_count = (
            len(prefetched_parts)
            if prefetched_parts is not None
            else expense.parts.count()
        )

        for index, allocation in enumerate(allocations):
            if index < part_count:
                split_component_label = f"Split part {index + 1}"
            else:
                split_component_label = "Remainder"
            rows.append(
                ExpenseListRow(
                    allocation=allocation,
                    split_component_label=split_component_label,
                )
            )

    return rows


def _finalize_expense_rows(rows):
    finalized_rows: list[ExpenseListRow] = []

    for _, group in groupby(rows, key=lambda row: row.expense.pk):
        group_rows = list(group)
        group_size = len(group_rows)
        for index, row in enumerate(group_rows):
            finalized_rows.append(
                replace(
                    row,
                    group_size=group_size,
                    show_parent_cells=index == 0,
                )
            )

    return finalized_rows


def _expense_row_matches_search(row, search_query):
    lowered_query = search_query.lower()
    expense = row.expense
    searchable_values = [
        expense.receiver,
        expense.description,
        expense.category,
        expense.category_obj.name if expense.category_obj else "",
        row.category_name,
    ]
    return any(lowered_query in (value or "").lower() for value in searchable_values)


def _unique_expenses_from_rows(rows):
    seen_ids = set()
    visible_expenses = []

    for row in rows:
        expense = row.expense
        if expense.pk in seen_ids:
            continue
        seen_ids.add(expense.pk)
        visible_expenses.append(expense)

    return visible_expenses


@login_required
def expense_list(request):
    form = SortForm(request.GET or None, user=request.user)
    bulk_category_form = BulkCategoryUpdateForm(user=request.user)
    order_by = "-date"  # default order
    category_filter_value = ""
    search_query = ""
    active_category = None
    category_ids = None

    if form.is_valid():
        order_by = form.cleaned_data.get("order_by") or "-date"
        category_filter_value = form.cleaned_data.get("category_filter") or ""
        search_query = form.cleaned_data.get("search", "").strip()

    today = date.today()
    month_param = request.GET.get("month", "")
    is_all = month_param == "all"

    active_month_date = today.replace(day=1)
    if not is_all and month_param:
        try:
            active_month_date = date.fromisoformat(month_param + "-01")
        except ValueError:
            pass

    prev_month_str = _add_months(active_month_date, -1).strftime("%Y-%m")
    next_month_date = _add_months(active_month_date, 1)
    next_month_str = next_month_date.strftime("%Y-%m")
    is_current_month = (
        active_month_date.year == today.year and active_month_date.month == today.month
    )
    active_month_label = active_month_date.strftime("%B %Y")

    expenses_queryset = (
        Expense.objects.filter(user=request.user)
        .select_related(
            "category_obj",
            "category_obj__parent",
            "category_obj__parent__parent",
            "category_obj__parent__parent__parent",
            "category_obj__parent__parent__parent__parent",
            "split_rule",
        )
        .prefetch_related(
            "parts__category_obj",
            "parts__category_obj__parent",
            "parts__category_obj__parent__parent",
            "parts__category_obj__parent__parent__parent",
            "parts__category_obj__parent__parent__parent__parent",
        )
        .order_by(order_by)
    )

    if not is_all:
        expenses_queryset = expenses_queryset.filter(
            date__year=active_month_date.year,
            date__month=active_month_date.month,
        )

    if search_query:
        expenses_queryset = expenses_queryset.filter(
            Q(receiver__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(category__icontains=search_query)
            | Q(category_obj__name__icontains=search_query)
            | Q(parts__category_obj__name__icontains=search_query)
        ).distinct()

    expenses = list(expenses_queryset)

    if category_filter_value == UNCATEGORIZED_SENTINEL:
        expenses = [expense for expense in expenses if is_uncategorized_expense(expense)]
        active_category = "Uncategorized"
    elif category_filter_value:
        try:
            cat = Category.objects.select_related(
                "parent", "parent__parent", "parent__parent__parent", "parent__parent__parent__parent"
            ).get(user=request.user, pk=int(category_filter_value))
            descendant_ids = cat.get_all_descendant_ids()
            category_ids = {cat.pk, *descendant_ids}
            expenses = [
                expense
                for expense in expenses
                if expense_matches_category_ids(expense, category_ids)
            ]
            has_descendants = bool(descendant_ids)
            active_category = (
                f"{cat.name} (+ subcategories)" if has_descendants else cat.name
            )
        except (Category.DoesNotExist, ValueError):
            pass

    expense_rows = _build_expense_rows(expenses)
    if search_query:
        expense_rows = [
            row
            for row in expense_rows
            if _expense_row_matches_search(row, search_query)
        ]

    if category_filter_value == UNCATEGORIZED_SENTINEL:
        expense_rows = [row for row in expense_rows if row.category is None]
    elif category_ids:
        expense_rows = [
            row
            for row in expense_rows
            if row.category and row.category.pk in category_ids
        ]

    expense_rows = _finalize_expense_rows(expense_rows)
    expenses = _unique_expenses_from_rows(expense_rows)

    summary = summarize_allocations(row.allocation for row in expense_rows)
    total_spent = summary["total_spent"]
    income = summary["income"]
    savings_total = summary["savings_total"]
    balance = summary["balance"]

    top_expenses = sorted(
        [
            row
            for row in expense_rows
            if row.amount < 0
            and not (
                row.category
                and row.category.category_type in NON_EXPENSE_CATEGORY_TYPES
            )
        ],
        key=lambda row: row.amount,
    )[:5]

    return render(
        request,
        "expenses/expense_list.html",
        {
            "expenses": expenses,
            "expense_rows": expense_rows,
            "total_spent": total_spent,
            "income": income,
            "savings_total": savings_total,
            "balance": balance,
            "top_expenses": top_expenses,
            "form": form,
            "bulk_category_form": bulk_category_form,
            "active_category": active_category,
            "active_month_label": active_month_label,
            "active_month_str": active_month_date.strftime("%Y-%m"),
            "prev_month_str": prev_month_str,
            "next_month_str": next_month_str,
            "is_current_month": is_current_month,
            "is_all": is_all,
            "order_by": order_by,
            "category_filter_value": category_filter_value,
            "search_query": search_query,
            "expense_list_query_string": _build_expense_list_query_string(
                {
                    "month": "all" if is_all else active_month_date.strftime("%Y-%m"),
                    "order_by": order_by,
                    "category_filter": category_filter_value,
                    "search": search_query,
                }
            ),
        },
    )


def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("expense_list")
    else:
        form = UserCreationForm()
    return render(request, "signup.html", {"form": form})


@login_required
def expense_add(request):
    expense = Expense(user=request.user)
    form = ExpenseForm(request.POST or None, instance=expense, user=request.user)
    total_amount = (
        _parse_decimal(request.POST.get("amount"))
        if request.method == "POST"
        else expense.amount
    )
    formset = _build_expense_part_formset(
        request=request,
        expense=expense,
        user=request.user,
        total_amount=total_amount,
    )

    if request.method == "POST" and form.is_valid():
        formset = _build_expense_part_formset(
            request=request,
            expense=expense,
            user=request.user,
            total_amount=form.cleaned_data["amount"],
        )
        if formset.is_valid():
            _validate_split_remainder(form, formset)
            if not form.errors:
                expense = form.save(commit=False)
                expense.user = request.user
                expense.save()
                _save_expense_parts(formset, expense)
                return redirect("expense_list")

    return render(
        request,
        "expenses/expense_form.html",
        {
            "form": form,
            "formset": formset,
            "title": "Add Expense",
            "split_summary": _build_split_summary(form, formset),
        },
    )


@login_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    return_url = _build_expense_list_url(
        request.POST if request.method == "POST" else request.GET
    )
    form = ExpenseForm(request.POST or None, instance=expense, user=request.user)
    total_amount = (
        _parse_decimal(request.POST.get("amount"))
        if request.method == "POST"
        else expense.amount
    )
    formset = _build_expense_part_formset(
        request=request,
        expense=expense,
        user=request.user,
        total_amount=total_amount,
    )

    if request.method == "POST" and form.is_valid():
        formset = _build_expense_part_formset(
            request=request,
            expense=expense,
            user=request.user,
            total_amount=form.cleaned_data["amount"],
        )
        if formset.is_valid():
            _validate_split_remainder(form, formset)
            if not form.errors:
                form.save()
                _save_expense_parts(formset, expense)
                return redirect(return_url)
    return render(
        request,
        "expenses/expense_form.html",
        {
            "form": form,
            "formset": formset,
            "title": "Edit Expense",
            "split_summary": _build_split_summary(form, formset),
            **_get_expense_form_context(request, return_url=return_url),
        },
    )


@login_required
def expense_bulk_category_update(request):
    if request.method != "POST":
        messages.error(
            request, "Bulk category updates must be submitted from the expense list."
        )
        return redirect("expense_list")

    redirect_url = _build_expense_list_url(request.POST)
    form = BulkCategoryUpdateForm(request.POST, user=request.user)

    if not form.is_valid():
        messages.error(request, _get_bulk_category_error_message(request, form))
        return redirect(redirect_url)

    selected_expenses = form.cleaned_data["expense_ids"]
    category = form.cleaned_data["category_obj"]
    updated_count = selected_expenses.update(
        category_obj=category,
        category=category.name,
    )

    messages.success(
        request,
        f"Updated {updated_count} expense{'s' if updated_count != 1 else ''} to {category.name}.",
    )
    return redirect(redirect_url)


@login_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    if request.method == "POST":
        expense.delete()
        return redirect("expense_list")
    return render(request, "expenses/expense_confirm_delete.html", {"expense": expense})


@login_required
def expense_delete_all(request):
    if request.method == "POST":
        Expense.objects.filter(user=request.user).delete()
        return redirect("expense_list")
    return render(request, "expenses/expense_confirm_delete_all.html")


@login_required
def upload_csv(request):
    if request.method == "POST":
        form = CSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            importer = get_importer(form.cleaned_data["import_format"])
            rows = importer.read_rows(request.FILES["file"])

            total_count = 0
            categorized_count = 0
            uncategorized_expenses = []

            for row in rows:
                parsed = importer.parse_row(row)

                match = categorize_from_sources(
                    ("receiver", parsed.receiver),
                    ("description", parsed.description),
                    user=request.user,
                )

                expense = Expense(
                    user=request.user,
                    date=parsed.date,
                    category=parsed.category,
                    category_obj=match.category,
                    description=parsed.description,
                    amount=parsed.amount,
                    receiver=parsed.receiver,
                )
                expense.save()
                total_count += 1

                if match.category:
                    categorized_count += 1
                else:
                    uncategorized_expenses.append(
                        {
                            "id": expense.pk,
                            "date": parsed.date,
                            "receiver": parsed.receiver,
                            "description": parsed.description,
                            "amount": str(parsed.amount),
                        }
                    )

            request.session["import_results"] = {
                "total": total_count,
                "categorized": categorized_count,
                "uncategorized": total_count - categorized_count,
                "uncategorized_expenses": uncategorized_expenses[:50],
            }

            return redirect("import_summary")
    else:
        form = CSVUploadForm()

    return render(request, "expenses/upload_csv.html", {"form": form})


@login_required
def show_expenses_amount(request):
    expenses = Expense.objects.filter(user=request.user)
    total_amount = sum(expense.amount for expense in expenses)
    return render(
        request,
        "expenses/total_expenses.html",
        {"total_amount": total_amount},
    )


@login_required
def category_list(request):
    """List the current user's categories as an ordered flat tree."""

    def build_flat_tree(root_queryset) -> list[tuple]:
        """
        Return (category, depth) pairs ordered so each parent is immediately
        followed by all its children (recursively), alphabetically within each level.
        Loads the full subtree efficiently using a single query + Python grouping.
        """
        root_ids = list(root_queryset.values_list("pk", flat=True))
        if not root_ids:
            return []

        # Load all categories in the same tree(s) in one query
        all_cats = list(
            Category.objects.filter(
                models.Q(pk__in=root_ids)
                | models.Q(parent_id__in=root_ids)
                | models.Q(parent__parent_id__in=root_ids)
                | models.Q(parent__parent__parent_id__in=root_ids)
                | models.Q(parent__parent__parent__parent_id__in=root_ids)
            ).select_related(
                "parent", "parent__parent", "parent__parent__parent", "parent__parent__parent__parent"
            )
        )

        by_parent: dict[int | None, list] = {}
        for cat in all_cats:
            by_parent.setdefault(cat.parent_id, []).append(cat)

        for children in by_parent.values():
            children.sort(key=lambda c: c.name.lower())

        result: list[tuple] = []

        def traverse(parent_id, depth):
            for cat in by_parent.get(parent_id, []):
                # Only start from actual roots of this queryset
                if parent_id is None and cat.pk not in root_ids:
                    continue
                result.append((cat, depth))
                traverse(cat.pk, depth + 1)

        traverse(None, 1)
        return result

    user_roots = Category.objects.filter(user=request.user, parent__isnull=True)

    return render(
        request,
        "expenses/category_list.html",
        {
            "category_tree": build_flat_tree(user_roots),
        },
    )

#TODO: These sync functions could be moved somewhere else
def run_category_sync(user):
    uncategorized_results = sync_uncategorized_expenses(user)
    upgrade_results = upgrade_categorized_expenses(user)
    return {**uncategorized_results, **upgrade_results}


def sync_uncategorized_expenses(user):
    uncategorized_expenses = Expense.objects.filter(
        user=user, category_obj__isnull=True
    )
    total_uncategorized = uncategorized_expenses.count()
    updated_count = 0
    updated_expenses = []
    still_uncategorized = []

    for expense in uncategorized_expenses.iterator():
        match = categorize_from_sources(
            ("receiver", expense.receiver),
            ("description", expense.description),
            user=user,
        )

        if match.category:
            expense.category_obj = match.category
            expense.category = match.category.name
            expense.save(update_fields=["category_obj", "category"])
            updated_count += 1

            if len(updated_expenses) < PREVIEW_LIMIT:
                updated_expenses.append(
                    {
                        "id": expense.pk,
                        "date": expense.date.strftime("%Y-%m-%d"),
                        "receiver": expense.receiver,
                        "description": expense.description,
                        "amount": str(expense.amount),
                        "category": match.category.name,
                        "matched_keyword": match.keyword,
                        "matched_from": match.source,
                    }
                )

        elif len(still_uncategorized) < PREVIEW_LIMIT:
            still_uncategorized.append(
                {
                    "id": expense.pk,
                    "date": expense.date.strftime("%Y-%m-%d"),
                    "receiver": expense.receiver,
                    "description": expense.description,
                    "amount": str(expense.amount),
                }
            )

    return {
        "total_uncategorized_before": total_uncategorized,
        "updated_count": updated_count,
        "remaining_uncategorized": total_uncategorized - updated_count,
        "updated_expenses": updated_expenses,
        "still_uncategorized": still_uncategorized,
    }


def can_upgrade_category(current, candidate):
    if candidate.pk == current.pk:
        return False
    if candidate.get_depth() <= current.get_depth():
        return False
    if candidate.get_root().pk != current.get_root().pk:
        return False
    return True


def upgrade_categorized_expenses(user):
    categorized_expenses = Expense.objects.filter(
        user=user, category_obj__isnull=False
    ).select_related(
        "category_obj__parent",
        "category_obj__parent__parent",
        "category_obj__parent__parent__parent",
        "category_obj__parent__parent__parent__parent",
    )

    upgraded_count = 0
    upgraded_expenses = []

    for expense in categorized_expenses.iterator():
        match = categorize_from_sources(
            ("receiver", expense.receiver),
            ("description", expense.description),
            user=user,
        )

        if not match.category:
            continue

        current = expense.category_obj
        candidate = match.category

        if not can_upgrade_category(current, candidate):
            continue

        old_category_name = current.name
        expense.category_obj = candidate
        expense.category = candidate.name
        expense.save(update_fields=["category_obj", "category"])
        upgraded_count += 1

        if len(upgraded_expenses) < PREVIEW_LIMIT:
            upgraded_expenses.append(
                {
                    "id": expense.pk,
                    "date": expense.date.strftime("%Y-%m-%d"),
                    "receiver": expense.receiver,
                    "description": expense.description,
                    "amount": str(expense.amount),
                    "old_category": old_category_name,
                    "new_category": candidate.name,
                    "matched_keyword": match.keyword,
                }
            )

    return {
        "upgraded_count": upgraded_count,
        "upgraded_expenses": upgraded_expenses,
    }

@login_required
def sync_categories(request):
    if request.method != "POST":
        messages.error(request, "Category sync must be started with the sync button.")
        return redirect("category_list")

    request.session["sync_results"] = run_category_sync(request.user)
    return redirect("sync_summary")

@login_required
def category_add(request):
    """Add a new category."""
    category_instance = Category(user=request.user)
    if request.method == "POST":
        form = CategoryForm(request.POST, user=request.user, instance=category_instance)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.save()
            messages.success(
                request, f"Category '{category.name}' created successfully!"
            )
            return redirect("category_list")
    else:
        form = CategoryForm(user=request.user, instance=category_instance)
    return render(
        request,
        "expenses/category_form.html",
        {"form": form, "title": "Add Category"},
    )


@login_required
def category_edit(request, pk):
    """Edit one of the current user's categories."""
    category = get_object_or_404(Category, pk=pk, user=request.user)

    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(
                request, f"Category '{category.name}' updated successfully!"
            )
            return redirect("category_list")
    else:
        form = CategoryForm(instance=category, user=request.user)

    return render(
        request,
        "expenses/category_form.html",
        {"form": form, "title": f"Edit Category: {category.name}"},
    )


@login_required
def category_delete(request, pk):
    """Delete one of the current user's categories."""
    category = get_object_or_404(Category, pk=pk, user=request.user)

    if request.method == "POST":
        category_name = category.name
        category.delete()
        messages.success(request, f"Category '{category_name}' deleted successfully!")
        return redirect("category_list")

    return render(
        request,
        "expenses/category_confirm_delete.html",
        {"category": category},
    )


@login_required
def import_summary(request):
    """Display import results with categorization summary."""
    import_results = request.session.get(
        "import_results",
        {
            "total": 0,
            "categorized": 0,
            "uncategorized": 0,
            "uncategorized_expenses": [],
        },
    )
    shown_uncategorized = len(import_results.get("uncategorized_expenses", []))
    extra_uncategorized = max(
        0, import_results.get("uncategorized", 0) - shown_uncategorized
    )

    # Clear from session after display
    if "import_results" in request.session:
        del request.session["import_results"]

    return render(
        request,
        "expenses/import_summary.html",
        {
            "import_results": import_results,
            "extra_uncategorized": extra_uncategorized,
        },
    )


@login_required
def sync_summary(request):
    """Display category sync results with affected expenses."""
    sync_results = request.session.get(
        "sync_results",
        {
            "total_uncategorized_before": 0,
            "updated_count": 0,
            "remaining_uncategorized": 0,
            "updated_expenses": [],
            "still_uncategorized": [],
            "upgraded_count": 0,
            "upgraded_expenses": [],
        },
    )
    # Back-compat: session data from an older sync won't have these keys
    sync_results.setdefault("upgraded_count", 0)
    sync_results.setdefault("upgraded_expenses", [])

    extra_updated = max(
        0, sync_results["updated_count"] - len(sync_results["updated_expenses"])
    )
    extra_remaining = max(
        0,
        sync_results["remaining_uncategorized"]
        - len(sync_results["still_uncategorized"]),
    )
    extra_upgraded = max(
        0, sync_results["upgraded_count"] - len(sync_results["upgraded_expenses"])
    )

    if "sync_results" in request.session:
        del request.session["sync_results"]

    return render(
        request,
        "expenses/sync_summary.html",
        {
            "sync_results": sync_results,
            "extra_updated": extra_updated,
            "extra_remaining": extra_remaining,
            "extra_upgraded": extra_upgraded,
        },
    )
