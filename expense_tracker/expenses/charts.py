from django.db.models import Sum
from django.db.models.functions import TruncMonth

import plotly.graph_objects as go
from plotly.offline import plot

from .models import Category, Expense


NON_EXPENSE_CATEGORY_TYPES = (
    Category.CATEGORY_TYPE_SAVING,
    Category.CATEGORY_TYPE_TRANSFER,
)


def create_cumulative_graph(user):
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
        go.Scatter(
            x=dates,
            y=cumulative_amounts,
            mode="lines",
            name="Cumulative",
            line=dict(color="red", width=2),
            yaxis="y2",
        )
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


def create_monthly_comparison(user):
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
    fig.add_trace(go.Bar(x=months, y=amounts, marker=dict(color="steelblue")))

    fig.update_layout(
        title="Monthly Spending Comparison",
        xaxis_title="Month",
        yaxis_title="Total Spent (€)",
        hovermode="x",
        height=400,
    )

    return plot(fig, output_type="div", include_plotlyjs=False)


def create_category_breakdown(user):
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
        go.Pie(
            labels=categories,
            values=amounts,
            hovertemplate="<b>%{label}</b><br>€%{value:.2f}<br>%{percent}",
        )
    )

    fig.update_layout(
        title="Spending by Category",
        height=400,
    )

    return plot(fig, output_type="div", include_plotlyjs=False)


def create_income_vs_expenses(user):
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
            .aggregate(total=Sum("user_share"))["total"]
            or 0
        )
        day_income = (
            Expense.objects.filter(user=user, date=item["date"], amount__gt=0)
            .aggregate(total=Sum("user_share"))["total"]
            or 0
        )

        expenses_cumsum += abs(day_expenses)
        income_cumsum += day_income

        expenses_list.append(expenses_cumsum)
        income_list.append(income_cumsum)
        balance_list.append(income_cumsum - expenses_cumsum)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=expenses_list,
            mode="lines",
            name="Cumulative Expenses",
            line=dict(color="red"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=income_list,
            mode="lines",
            name="Cumulative Income",
            line=dict(color="green"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=balance_list,
            mode="lines",
            name="Balance",
            line=dict(color="blue", dash="dash"),
        )
    )

    fig.update_layout(
        title="Income vs Expenses Over Time",
        xaxis_title="Date",
        yaxis_title="Amount (€)",
        hovermode="x unified",
        height=400,
    )

    return plot(fig, output_type="div", include_plotlyjs=False)
