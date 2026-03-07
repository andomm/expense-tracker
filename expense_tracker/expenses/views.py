from django.shortcuts import get_object_or_404, render, redirect

from .forms import ExpenseForm, CSVUploadForm, SortForm, CategoryForm

from .models import Expense, Category, ExpenseSplitRule
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from decimal import Decimal

import csv
from io import TextIOWrapper
from django.contrib import messages
from django.db.models import Sum, Q
import plotly.graph_objects as go
from plotly.offline import plot
from django.db.models.functions import TruncMonth
from collections import defaultdict

NON_EXPENSE_CATEGORY_TYPES = (
    Category.CATEGORY_TYPE_SAVING,
    Category.CATEGORY_TYPE_TRANSFER,
)


def categorize_expense_by_description(description, user):
    """
    Match an expense text to a category using keyword matching.
    
    Returns:
        (category_obj, matched_keyword) if match found
        (None, None) if no match
    """
    if not description or not description.strip():
        return None, None
    
    description_lower = description.lower()
    
    # Get all categories (system + user's custom)
    categories = Category.objects.filter(
        Q(is_system=True) | Q(user=user)
    ).exclude(keywords='')
    
    # Try to find a matching category
    for category in categories:
        keywords = category.get_keywords_list()
        for keyword in keywords:
            if keyword in description_lower:
                return category, keyword
    
    return None, None




def _create_cumulative_graph(user):
    """Create enhanced cumulative expenses graph with daily bars and cumulative line."""
    daily_totals = (
        Expense.objects.filter(user=user, amount__lt=0)
        .exclude(category_obj__category_type__in=NON_EXPENSE_CATEGORY_TYPES)
        .values("date")
        .annotate(total_spent=Sum("user_share"))
        .order_by("date")
    )

    dates = []
    daily_amounts = []
    cumulative_amounts = []
    cumulative_sum = 0

    for expense in daily_totals:
        dates.append(expense["date"].strftime("%Y-%m-%d"))
        daily_amount = abs(expense["total_spent"])
        daily_amounts.append(daily_amount)
        cumulative_sum += daily_amount
        cumulative_amounts.append(cumulative_sum)

    fig = go.Figure()
    fig.add_trace(
        go.Bar(x=dates, y=daily_amounts, name="Daily Spending", opacity=0.6)
    )
    fig.add_trace(
        go.Scatter(x=dates, y=cumulative_amounts, mode="lines", name="Cumulative", 
                  line=dict(color="red", width=2), yaxis="y2")
    )
    
    fig.update_layout(
        title="Cumulative Expenses Over Time",
        xaxis_title="Date",
        yaxis_title="Daily Amount Spent (€)",
        yaxis2=dict(title="Cumulative Total (€)", overlaying="y", side="right"),
        hovermode="x unified",
        height=400,
    )
    
    return plot(fig, output_type="div", include_plotlyjs=False)


def _create_monthly_comparison(user):
    """Create monthly comparison bar chart."""
    monthly_totals = (
        Expense.objects.filter(user=user, amount__lt=0)
        .exclude(category_obj__category_type__in=NON_EXPENSE_CATEGORY_TYPES)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total_spent=Sum("user_share"))
        .order_by("month")
    )

    months = []
    amounts = []
    
    for item in monthly_totals:
        months.append(item["month"].strftime("%b %Y"))
        amounts.append(abs(item["total_spent"]))

    fig = go.Figure()
    fig.add_trace(
        go.Bar(x=months, y=amounts, marker=dict(color="steelblue"))
    )
    
    fig.update_layout(
        title="Monthly Spending Comparison",
        xaxis_title="Month",
        yaxis_title="Total Spent (€)",
        hovermode="x",
        height=400,
    )
    
    return plot(fig, output_type="div", include_plotlyjs=False)


def _create_category_breakdown(user):
    """Create category-based pie chart."""
    category_totals = (
        Expense.objects.filter(user=user, amount__lt=0)
        .exclude(category_obj__category_type__in=NON_EXPENSE_CATEGORY_TYPES)
        .values("category_obj__name")
        .annotate(total_spent=Sum("user_share"))
        .order_by("-total_spent")
    )

    categories = []
    amounts = []
    
    for item in category_totals:
        cat_name = item["category_obj__name"] or "Uncategorized"
        categories.append(cat_name)
        amounts.append(abs(item["total_spent"]))

    fig = go.Figure()
    fig.add_trace(
        go.Pie(labels=categories, values=amounts, hovertemplate="<b>%{label}</b><br>€%{value:.2f}<br>%{percent}")
    )
    
    fig.update_layout(
        title="Spending by Category",
        height=400,
    )
    
    return plot(fig, output_type="div", include_plotlyjs=False)


def _create_income_vs_expenses(user):
    """Create income vs expenses chart with cumulative balance."""
    daily_totals = (
        Expense.objects.filter(user=user)
        .values("date")
        .annotate(total=Sum("user_share"))
        .order_by("date")
    )

    dates = []
    expenses_cumsum = 0
    income_cumsum = 0
    expenses_list = []
    income_list = []
    balance_list = []

    for item in daily_totals:
        date_str = item["date"].strftime("%Y-%m-%d")
        dates.append(date_str)
        
        day_expenses = (
            Expense.objects.filter(user=user, date=item["date"], amount__lt=0)
            .exclude(category_obj__category_type__in=NON_EXPENSE_CATEGORY_TYPES)
            .aggregate(total=Sum("user_share"))["total"] or 0
        )
        day_income = (
            Expense.objects.filter(user=user, date=item["date"], amount__gt=0)
            .aggregate(total=Sum("user_share"))["total"] or 0
        )
        
        expenses_cumsum += abs(day_expenses)
        income_cumsum += day_income
        
        expenses_list.append(expenses_cumsum)
        income_list.append(income_cumsum)
        balance_list.append(income_cumsum - expenses_cumsum)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=dates, y=expenses_list, mode="lines", name="Cumulative Expenses",
                  line=dict(color="red"))
    )
    fig.add_trace(
        go.Scatter(x=dates, y=income_list, mode="lines", name="Cumulative Income",
                  line=dict(color="green"))
    )
    fig.add_trace(
        go.Scatter(x=dates, y=balance_list, mode="lines", name="Balance",
                  line=dict(color="blue", dash="dash"))
    )
    
    fig.update_layout(
        title="Income vs Expenses Over Time",
        xaxis_title="Date",
        yaxis_title="Amount (€)",
        hovermode="x unified",
        height=400,
    )
    
    return plot(fig, output_type="div", include_plotlyjs=False)


@login_required
def expenses_per_month(request):
    monthly_totals = (
        Expense.objects.filter(user=request.user, amount__lt=0)
        .exclude(category_obj__category_type__in=NON_EXPENSE_CATEGORY_TYPES)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total_spent=Sum("user_share"))
        .order_by("month")
    )

    cumulative_graph = _create_cumulative_graph(request.user)
    monthly_comparison = _create_monthly_comparison(request.user)
    category_breakdown = _create_category_breakdown(request.user)
    income_vs_expenses = _create_income_vs_expenses(request.user)

    return render(
        request,
        "expenses/expenses_per_month.html",
        {
            "expenses_per_month": monthly_totals,
            "cumulative_graph": cumulative_graph,
            "monthly_comparison": monthly_comparison,
            "category_breakdown": category_breakdown,
            "income_vs_expenses": income_vs_expenses,
        },
    )


@login_required
def expense_list(request):
    form = SortForm(request.GET or None)
    order_by = "-date"  # default order

    if form.is_valid():
        order_by = form.cleaned_data.get("order_by") or "-date"

    expenses = Expense.objects.filter(user=request.user).order_by(order_by)
    # Use user_share for accurate personal calculations
    total_spent = sum(
        expense.user_share
        for expense in expenses
        if expense.user_share
        and expense.amount < 0
        and not (
            expense.category_obj
            and expense.category_obj.category_type in NON_EXPENSE_CATEGORY_TYPES
        )
    )
    income = sum(expense.user_share for expense in expenses if expense.user_share and expense.amount > 0)
    balance = total_spent + income

    top_expenses = (
        expenses.filter(amount__lt=0)
        .exclude(category_obj__category_type__in=NON_EXPENSE_CATEGORY_TYPES)
        .order_by("amount")[:5]
    )

    return render(
        request,
        "expenses/expense_list.html",
        {
            "expenses": expenses,
            "total_spent": total_spent,
            "income": income,
            "balance": balance,
            "top_expenses": top_expenses,
            "form": form,
        },
    )


def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # log in the user right after signup
            return redirect("expense_list")
    else:
        form = UserCreationForm()
    return render(request, "signup.html", {"form": form})


@login_required
def expense_add(request):
    if request.method == "POST":
        form = ExpenseForm(request.POST, user=request.user)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.user = request.user
            expense.save()
            return redirect("expense_list")
    else:
        form = ExpenseForm(user=request.user)
    return render(
        request, "expenses/expense_form.html", {"form": form, "title": "Add Expense"}
    )


@login_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    if request.method == "POST":
        form = ExpenseForm(request.POST, instance=expense, user=request.user)
        if form.is_valid():
            form.save()
            return redirect("expense_list")
    else:
        form = ExpenseForm(instance=expense, user=request.user)
    return render(
        request, "expenses/expense_form.html", {"form": form, "title": "Edit Expense"}
    )


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
            csv_file = TextIOWrapper(request.FILES["file"].file, encoding="utf-8")
            reader = csv.DictReader(csv_file, delimiter=";")
            
            # Track results
            total_count = 0
            categorized_count = 0
            uncategorized_expenses = []
            
            for row in reader:
                # Adjust these keys to match your CSV columns
                row["Määrä EUROA"] = row["Määrä EUROA"].replace(",", ".")
                
                # Two-stage matching: try receiver first, fall back to description.
                receiver = row.get("Saaja/Maksaja", "")
                description = row.get("Viesti", "")
                matched_from = None
                category_obj, matched_keyword = categorize_expense_by_description(receiver, request.user)
                if category_obj:
                    matched_from = "receiver"
                else:
                    category_obj, matched_keyword = categorize_expense_by_description(description, request.user)
                    if category_obj:
                        matched_from = "description"
                
                if category_obj:
                    categorized_count += 1
                else:
                    # Track uncategorized expenses for feedback
                    uncategorized_expenses.append({
                        'date': row.get("Arvopäivä", ""),
                        'receiver': receiver,
                        'description': description,
                        'amount': row.get("Määrä EUROA", ""),
                    })
                
                amount = Decimal(row["Määrä EUROA"])
                expense = Expense(
                    user=request.user,
                    date=row["Arvopäivä"],
                    category=row.get("Selitys", ""),  # Keep for reference
                    category_obj=category_obj,  # NEW: Smart matched category
                    description=description,
                    amount=amount,
                    receiver=receiver,
                )
                # user_share will be auto-set by save() method
                expense.save()
                total_count += 1
            
            # Store results in session for import summary page
            request.session['import_results'] = {
                'total': total_count,
                'categorized': categorized_count,
                'uncategorized': total_count - categorized_count,
                'uncategorized_expenses': uncategorized_expenses[:50],  # Limit to first 50
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
    """List all categories (system + user custom)."""
    system_categories = Category.objects.filter(is_system=True)
    user_categories = Category.objects.filter(user=request.user)
    return render(
        request,
        "expenses/category_list.html",
        {
            "system_categories": system_categories,
            "user_categories": user_categories,
        },
    )


@login_required
def sync_categories(request):
    """Apply current keyword rules to uncategorized existing expenses."""
    if request.method != "POST":
        messages.error(request, "Category sync must be started with the sync button.")
        return redirect("category_list")

    uncategorized_expenses = Expense.objects.filter(user=request.user, category_obj__isnull=True)
    total_uncategorized = uncategorized_expenses.count()
    updated_count = 0
    updated_expenses = []
    still_uncategorized = []

    for expense in uncategorized_expenses.iterator():
        matched_from = None
        category_obj, matched_keyword = categorize_expense_by_description(expense.receiver, request.user)
        if category_obj:
            matched_from = "receiver"
        else:
            category_obj, matched_keyword = categorize_expense_by_description(expense.description, request.user)
            if category_obj:
                matched_from = "description"
        if category_obj:
            expense.category_obj = category_obj
            expense.category = category_obj.name
            expense.save(update_fields=["category_obj", "category"])
            updated_count += 1
            if len(updated_expenses) < 50:
                updated_expenses.append(
                    {
                        "date": expense.date.strftime("%Y-%m-%d"),
                        "receiver": expense.receiver,
                        "description": expense.description,
                        "amount": str(expense.amount),
                        "category": category_obj.name,
                        "matched_keyword": matched_keyword,
                        "matched_from": matched_from,
                    }
                )
        elif len(still_uncategorized) < 50:
            still_uncategorized.append(
                {
                    "date": expense.date.strftime("%Y-%m-%d"),
                    "receiver": expense.receiver,
                    "description": expense.description,
                    "amount": str(expense.amount),
                }
            )

    request.session["sync_results"] = {
        "total_uncategorized_before": total_uncategorized,
        "updated_count": updated_count,
        "remaining_uncategorized": total_uncategorized - updated_count,
        "updated_expenses": updated_expenses,
        "still_uncategorized": still_uncategorized,
    }
    return redirect("sync_summary")


@login_required
def category_add(request):
    """Add a new custom category."""
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.is_system = False
            category.save()
            messages.success(request, f"Category '{category.name}' created successfully!")
            return redirect("category_list")
    else:
        form = CategoryForm()
    return render(
        request,
        "expenses/category_form.html",
        {"form": form, "title": "Add Category"},
    )


@login_required
def category_edit(request, pk):
    """Edit a category's keywords (user categories and system categories)."""
    # Allow editing system categories or user's own categories
    if request.user.is_staff:
        category = get_object_or_404(Category, pk=pk)
    else:
        category = get_object_or_404(Category, pk=pk, user=request.user)
    
    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, f"Category '{category.name}' updated successfully!")
            return redirect("category_list")
    else:
        form = CategoryForm(instance=category)
    
    return render(
        request,
        "expenses/category_form.html",
        {"form": form, "title": f"Edit Category: {category.name}"},
    )


@login_required
def category_delete(request, pk):
    """Delete a custom category (system categories can't be deleted)."""
    category = get_object_or_404(Category, pk=pk, user=request.user)
    
    if category.is_system:
        messages.error(request, "System categories cannot be deleted.")
        return redirect("category_list")
    
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
    import_results = request.session.get('import_results', {
        'total': 0,
        'categorized': 0,
        'uncategorized': 0,
        'uncategorized_expenses': [],
    })
    shown_uncategorized = len(import_results.get('uncategorized_expenses', []))
    extra_uncategorized = max(0, import_results.get('uncategorized', 0) - shown_uncategorized)
    
    # Clear from session after display
    if 'import_results' in request.session:
        del request.session['import_results']
    
    return render(request, "expenses/import_summary.html", {
        "import_results": import_results,
        "extra_uncategorized": extra_uncategorized,
    })


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
        },
    )
    extra_updated = max(0, sync_results["updated_count"] - len(sync_results["updated_expenses"]))
    extra_remaining = max(
        0,
        sync_results["remaining_uncategorized"] - len(sync_results["still_uncategorized"]),
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
        },
    )
