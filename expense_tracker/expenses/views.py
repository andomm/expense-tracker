from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from .allocations import build_yearly_spending_summary
from .category_sync import latest_category_sync, record_category_sync
from .category_tree import category_groups
from .csv_import import latest_import, record_import
from .expense_list import ExpenseFilters, month_key, picker_years, read_expense_list, shift_month
from .expense_save import save_expense, validate_expense
from .importers import CSVError

from .forms import (
    BulkCategoryUpdateForm,
    CSVUploadForm,
    CategoryForm,
    ExpenseForm,
    SplitRowFormSet,
    SortForm,
)

from .models import Expense, Category

from expenses.charts import (
    create_category_breakdown,
    create_cumulative_graph,
    create_income_vs_expenses,
    create_monthly_comparison,
)

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

    prev_month_str = shift_month(active_month_date, -1).strftime("%Y-%m")
    next_month_date = shift_month(active_month_date, 1)
    next_month_str = next_month_date.strftime("%Y-%m")
    is_current_month = (
        active_month_date.year == today.year and active_month_date.month == today.month
    )
    active_month_label = active_month_date.strftime("%B %Y")

    yearly_totals = build_yearly_spending_summary(
        Expense.objects.filter(user=request.user)
        .select_related(
            "category_obj",
            "category_obj__parent",
            "category_obj__parent__parent",
            "category_obj__parent__parent__parent",
            "category_obj__parent__parent__parent__parent",
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
            "yearly_summary": yearly_totals,
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
        amount = Decimal(str(value))
        return amount if amount.is_finite() else None
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


def _build_split_summary(form, formset):
    if not formset.forms:
        return None

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
        category = form.instance.category_obj

    return {
        "split_total": split_total,
        "remainder": remainder,
        "remainder_category_name": category.name if category else "Uncategorized",
    }


@login_required
def expense_list(request):
    form = SortForm(request.GET or None, user=request.user)
    filters = ExpenseFilters.from_params(request.GET, form)
    listing = read_expense_list(request.user, filters, form.categories)
    active_month = filters.month

    return render(
        request,
        "expenses/expense_list.html",
        {
            "expenses": [row.expense for row in listing.rows],
            "expense_rows": listing.rows,
            **listing.summary(),
            "top_expenses": listing.top_expenses(),
            "form": form,
            "bulk_category_form": BulkCategoryUpdateForm(user=request.user),
            "active_category": listing.active_category,
            "active_month_label": active_month.strftime("%B %Y"),
            "active_month_str": month_key(active_month),
            "prev_month_str": filters.previous,
            "next_month_str": filters.next,
            "is_current_month": active_month == filters.current_month,
            "is_all": filters.is_all,
            "order_by": filters.order_by,
            "category_filter_value": filters.category_filter,
            "search_query": filters.search,
            "picker_years": picker_years(request.user, filters.current_month),
            "active_month_num": active_month.month,
            "active_year": active_month.year,
            "expense_list_query_string": _build_expense_list_query_string(
                {
                    "month": filters.period,
                    "order_by": filters.order_by,
                    "category_filter": filters.category_filter,
                    "search": filters.search,
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
    return _legacy_expense_form(request, Expense(user=request.user), title="Add Expense")


@login_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    return _legacy_expense_form(request, expense, title="Edit Expense")


def _legacy_expense_form(request, expense, *, title):
    data = request.POST if request.method == "POST" else None
    return_url = None
    if expense.pk:
        return_url = _build_expense_list_url(data if data is not None else request.GET)
    form = ExpenseForm(data, instance=expense, user=request.user)
    formset = SplitRowFormSet(data, prefix="parts", form_kwargs={"user": request.user})
    if data is not None and validate_expense(form, formset):
        save_expense(form, formset)
        return redirect(return_url or "expense_list")
    return render(
        request,
        "expenses/expense_form.html",
        {
            "form": form,
            "formset": formset,
            "title": title,
            "split_summary": _build_split_summary(form, formset),
            **(
                _get_expense_form_context(request, return_url=return_url)
                if return_url else {}
            ),
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
def expense_bulk_delete(request):
    if request.method != "POST":
        return redirect("expense_list")

    redirect_url = _build_expense_list_url(request.POST)
    expense_ids = request.POST.getlist("expense_ids")

    if expense_ids:
        Expense.objects.filter(user=request.user, pk__in=expense_ids).delete()

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
    expenses = Expense.objects.filter(user=request.user)
    submitted = request.method == "POST"
    if submitted and request.POST.get("confirmation") == "DELETE":
        expenses.delete()
        return redirect("expense_list")
    return render(
        request,
        "expenses/expense_confirm_delete_all.html",
        {"count": expenses.count(), "invalid_confirmation": submitted},
        status=422 if submitted else 200,
    )


@login_required
@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
def upload_csv(request):
    submitted = request.method == "POST"
    form = CSVUploadForm(request.POST, request.FILES) if submitted else CSVUploadForm()
    if submitted and form.is_valid():
        try:
            record_import(request, **form.cleaned_data)
        except CSVError as error:
            form.add_error("file", str(error))
        else:
            return redirect("import_summary")
    return render(
        request, "expenses/upload_csv.html", {"form": form}, status=422 if submitted else 200
    )


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
    """List the current user's categories as collapsible groups."""

    return render(
        request,
        "expenses/category_list.html",
        {"category_groups": category_groups(request.user)},
    )


@login_required
def sync_categories(request):
    if request.method != "POST":
        messages.error(request, "Category sync must be started with the sync button.")
        return redirect("category_list")

    record_category_sync(request)
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
@never_cache
@require_safe
def import_summary(request):
    return render(request, "expenses/import_summary.html", {"result": latest_import(request)})


@login_required
@never_cache
def sync_summary(request):
    """Render the retained Django result page with the shared sync report."""
    result = latest_category_sync(request) or {"counts": {}, "previews": {}}
    counts = result["counts"]
    previews = result["previews"]
    updated = previews.get("newly_categorized", {})
    upgraded = previews.get("upgraded", {})
    remaining = previews.get("still_uncategorized", {})
    return render(
        request,
        "expenses/sync_summary.html",
        {
            "sync_results": {
                "total_uncategorized_before": counts.get("uncategorized_before", 0),
                "updated_count": counts.get("newly_categorized", 0),
                "remaining_uncategorized": counts.get("still_uncategorized", 0),
                "upgraded_count": counts.get("upgraded", 0),
                "updated_expenses": updated.get("rows", []),
                "still_uncategorized": remaining.get("rows", []),
                "upgraded_expenses": upgraded.get("rows", []),
            },
            "extra_updated": updated.get("omitted", 0),
            "extra_remaining": remaining.get("omitted", 0),
            "extra_upgraded": upgraded.get("omitted", 0),
        },
    )
