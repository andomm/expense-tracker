"""Plotly adapter for the retained legacy Analytics page."""

from datetime import date

import plotly.graph_objects as go
from plotly.offline import plot

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


def render_daily_spending(rows: list[dict]) -> str:
    dates = [row["date"].isoformat() for row in rows]
    daily_amounts = [row["daily"] for row in rows]
    cumulative_amounts = [row["cumulative"] for row in rows]

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


def render_monthly_spending(rows: list[dict]) -> str:
    months = [date.fromisoformat(row["month"] + "-01").strftime("%b %Y") for row in rows]
    amounts = [row["total_spent"] for row in rows]

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


def render_category_breakdown(breakdown: dict) -> str:
    categories = [row["name"] for row in breakdown["rows"]]
    amounts = [row["amount"] for row in breakdown["rows"]]

    if not categories:
        return _render_chart(_empty_figure("No category data for the selected month."))

    fig = go.Figure()
    fig.add_trace(
        go.Pie(
            labels=categories,
            values=amounts,
            hole=0.58,
            sort=False,
            text=[f"{row['percent']:.2f}%" for row in breakdown["rows"]],
            textinfo="text",
            textposition="inside",
            marker=dict(
                colors=CHART_COLORWAY,
                line=dict(color="rgba(248, 250, 252, 0.95)", width=2),
            ),
            hovertemplate="<b>%{label}</b><br>Spent €%{value:,.2f}<br>%{text}<extra></extra>",
        )
    )
    fig.add_annotation(
        text=f"Total<br><b>€{breakdown['total']:,.2f}</b>",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=13, color=LIGHT_MUTED_TEXT),
    )

    fig.update_layout(
        _chart_layout(
            hovermode="closest",
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


def render_cash_flow(rows: list[dict]) -> str:
    dates = [row["date"].isoformat() for row in rows]
    expenses_list = [row["expenses"] for row in rows]
    income_list = [row["income"] for row in rows]
    balance_list = [row["balance"] for row in rows]

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
