from collections import defaultdict
from decimal import Decimal

import plotly.graph_objects as go
from plotly.offline import plot

from .allocations import (
    NON_EXPENSE_CATEGORY_TYPES,
    build_monthly_spending_summary,
    get_expense_allocations,
)
from .models import Category, Expense

CHART_FONT_FAMILY = "Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
CHART_COLORWAY = [
    "#6366f1",
    "#14b8a6",
    "#f59e0b",
    "#8b5cf6",
    "#ec4899",
    "#0ea5e9",
    "#84cc16",
    "#f97316",
]
LIGHT_TEXT_COLOR = "#0f172a"
LIGHT_MUTED_TEXT = "#475569"
LIGHT_GRID_COLOR = "rgba(148, 163, 184, 0.18)"
LIGHT_AXIS_COLOR = "rgba(148, 163, 184, 0.38)"


def _expense_queryset(user):
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


def _chart_layout(**overrides):
    layout = {
        "height": 360,
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "margin": dict(l=14, r=14, t=18, b=14),
        "font": dict(family=CHART_FONT_FAMILY, color=LIGHT_TEXT_COLOR, size=13),
        "colorway": CHART_COLORWAY,
        "legend": dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=12, color=LIGHT_MUTED_TEXT),
            bgcolor="rgba(0,0,0,0)",
            itemclick=False,
            itemdoubleclick=False,
        ),
        "hoverlabel": dict(
            bgcolor="#0f172a",
            bordercolor="#0f172a",
            font=dict(color="#f8fafc", size=12),
        ),
    }
    layout.update(overrides)
    return layout


def _axis_layout():
    return dict(
        showgrid=True,
        gridcolor=LIGHT_GRID_COLOR,
        zeroline=False,
        showline=True,
        linecolor=LIGHT_AXIS_COLOR,
        tickfont=dict(size=12, color=LIGHT_MUTED_TEXT),
        title_font=dict(size=12, color=LIGHT_MUTED_TEXT),
        automargin=True,
    )


def _empty_figure(message):
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(size=14, color=LIGHT_MUTED_TEXT),
    )
    fig.update_layout(
        _chart_layout(
            height=280,
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False,
        )
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _render_chart(fig):
    return plot(
        fig,
        output_type="div",
        include_plotlyjs=False,
        config={
            "displayModeBar": False,
            "displaylogo": False,
            "responsive": True,
        },
    )


def create_cumulative_graph(user):
    """Create enhanced cumulative expenses graph with daily bars and cumulative line."""
    daily_totals: dict = defaultdict(lambda: Decimal("0"))

    for expense in _expense_queryset(user):
        for allocation in get_expense_allocations(expense):
            category_type = (
                allocation.category.category_type
                if allocation.category
                else Category.CATEGORY_TYPE_EXPENSE
            )
            if category_type in NON_EXPENSE_CATEGORY_TYPES:
                continue
            daily_totals[expense.date] += allocation.amount

    dates = []
    daily_amounts = []
    cumulative_amounts = []
    cumulative_sum = 0

    for day, total_spent in sorted(daily_totals.items()):
        dates.append(day.strftime("%Y-%m-%d"))
        cumulative_sum += float(total_spent)
        daily_amounts.append(float(abs(total_spent)))
        cumulative_amounts.append(abs(cumulative_sum))

    if not dates:
        return _render_chart(_empty_figure("No spending data yet for this chart."))

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=dates,
            y=daily_amounts,
            name="Daily spending",
            marker=dict(color="rgba(99, 102, 241, 0.55)"),
            hovertemplate="<b>%{x}</b><br>Spent €%{y:,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=cumulative_amounts,
            mode="lines",
            name="Cumulative",
            line=dict(color="#f59e0b", width=3, shape="spline", smoothing=0.5),
            hovertemplate="<b>%{x}</b><br>Cumulative €%{y:,.2f}<extra></extra>",
            yaxis="y2",
        )
    )

    fig.update_layout(
        _chart_layout(
            yaxis=dict(_axis_layout(), tickprefix="€"),
            yaxis2=dict(
                _axis_layout(),
                tickprefix="€",
                overlaying="y",
                side="right",
                showgrid=False,
            ),
            xaxis=dict(_axis_layout(), tickangle=-20),
            hovermode="x unified",
        )
    )

    return _render_chart(fig)


def create_monthly_comparison(user):
    """Create monthly comparison bar chart."""
    monthly_totals = build_monthly_spending_summary(_expense_queryset(user))

    months = []
    amounts = []

    for item in monthly_totals:
        months.append(item["month"].strftime("%b %Y"))
        amounts.append(item["total_spent"])

    if not months:
        return _render_chart(_empty_figure("No monthly spending data yet."))

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=months,
            y=amounts,
            marker=dict(color="rgba(14, 165, 233, 0.82)"),
            hovertemplate="<b>%{x}</b><br>Total €%{y:,.2f}<extra></extra>",
        )
    )

    fig.update_layout(
        _chart_layout(
            xaxis=_axis_layout(),
            yaxis=dict(_axis_layout(), tickprefix="€"),
            bargap=0.35,
            hovermode="x",
        )
    )

    return _render_chart(fig)


def create_category_breakdown(
    user,
    *,
    active_month_date=None,
):
    """Create category-based pie chart for the selected month."""
    expenses = _expense_queryset(user)

    if active_month_date is not None:
        expenses = expenses.filter(
            date__year=active_month_date.year,
            date__month=active_month_date.month,
        )

    category_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for expense in expenses:
        for allocation in get_expense_allocations(expense):
            category_type = (
                allocation.category.category_type
                if allocation.category
                else Category.CATEGORY_TYPE_EXPENSE
            )
            if category_type in NON_EXPENSE_CATEGORY_TYPES:
                continue

            if allocation.category:
                root = allocation.category.get_root()
                category_name = root.name
            else:
                category_name = "Uncategorized"
            category_totals[category_name] += allocation.amount

    sorted_totals = sorted(
        category_totals.items(),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    categories = [name for name, _ in sorted_totals]
    amounts = [float(abs(amount)) for _, amount in sorted_totals]

    if not categories:
        return _render_chart(_empty_figure("No category data for the selected month."))

    fig = go.Figure()
    fig.add_trace(
        go.Pie(
            labels=categories,
            values=amounts,
            hole=0.58,
            sort=False,
            textinfo="percent",
            textposition="inside",
            marker=dict(
                colors=CHART_COLORWAY,
                line=dict(color="rgba(248, 250, 252, 0.95)", width=2),
            ),
            hovertemplate="<b>%{label}</b><br>Spent €%{value:,.2f}<br>%{percent}<extra></extra>",
        )
    )
    fig.add_annotation(
        text=f"Total<br><b>€{sum(amounts):,.2f}</b>",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=13, color=LIGHT_MUTED_TEXT),
    )

    fig.update_layout(
        _chart_layout(
            hovermode=False,
            margin=dict(l=10, r=10, t=10, b=24),
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.08,
                xanchor="left",
                x=0,
                font=dict(size=12, color=LIGHT_MUTED_TEXT),
                bgcolor="rgba(0,0,0,0)",
                itemclick=False,
                itemdoubleclick=False,
            ),
        )
    )

    return _render_chart(fig)


def create_income_vs_expenses(user):
    """Create income vs expenses chart with cumulative balance."""
    daily_expenses: dict = defaultdict(lambda: Decimal("0"))
    daily_income: dict = defaultdict(lambda: Decimal("0"))

    for expense in _expense_queryset(user):
        for allocation in get_expense_allocations(expense):
            category_type = (
                allocation.category.category_type
                if allocation.category
                else Category.CATEGORY_TYPE_EXPENSE
            )
            if category_type == Category.CATEGORY_TYPE_INCOME:
                daily_income[expense.date] += allocation.amount
            elif category_type not in NON_EXPENSE_CATEGORY_TYPES:
                daily_expenses[expense.date] += allocation.amount

    all_dates = sorted(set(daily_expenses) | set(daily_income))

    dates = []
    expenses_cumsum = 0
    income_cumsum = 0
    expenses_list = []
    income_list = []
    balance_list = []

    for day in all_dates:
        date_str = day.strftime("%Y-%m-%d")
        dates.append(date_str)

        expenses_cumsum += float(daily_expenses[day])
        income_cumsum += float(daily_income[day])

        expenses_list.append(abs(expenses_cumsum))
        income_list.append(income_cumsum)
        balance_list.append(income_cumsum + expenses_cumsum)

    if not dates:
        return _render_chart(_empty_figure("No income or spending data yet."))

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=expenses_list,
            mode="lines",
            name="Cumulative Expenses",
            line=dict(color="#f43f5e", width=3, shape="spline", smoothing=0.45),
            hovertemplate="<b>%{x}</b><br>Expenses €%{y:,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=income_list,
            mode="lines",
            name="Cumulative Income",
            line=dict(color="#10b981", width=3, shape="spline", smoothing=0.45),
            hovertemplate="<b>%{x}</b><br>Income €%{y:,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=balance_list,
            mode="lines",
            name="Balance",
            line=dict(color="#6366f1", width=3, dash="dash", shape="spline", smoothing=0.45),
            hovertemplate="<b>%{x}</b><br>Balance €%{y:,.2f}<extra></extra>",
        )
    )

    fig.update_layout(
        _chart_layout(
            xaxis=dict(_axis_layout(), tickangle=-20),
            yaxis=dict(_axis_layout(), tickprefix="€"),
            hovermode="x unified",
        )
    )

    return _render_chart(fig)
