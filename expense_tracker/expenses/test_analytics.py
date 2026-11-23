from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from .models import Category, Expense

INCOME = Category.CATEGORY_TYPE_INCOME
SAVING = Category.CATEGORY_TYPE_SAVING
TRANSFER = Category.CATEGORY_TYPE_TRANSFER


@pytest.fixture
def accounts(db, client):
    owner = User.objects.create_user(username="analytics-owner")
    other = User.objects.create_user(username="analytics-other")
    client.force_login(owner)
    return owner, other


@pytest.fixture
def transactions(accounts):
    owner, other = accounts
    housing = Category.objects.create(user=owner, name="Housing")
    rent = Category.objects.create(user=owner, name="Rent", parent=housing)
    income = Category.objects.create(user=owner, name="Salary", category_type=INCOME)
    saving = Category.objects.create(user=owner, name="Saving", category_type=SAVING)
    transfer = Category.objects.create(user=owner, name="Transfer", category_type=TRANSFER)
    for day, amount, share, category in [
        ("2025-12-29", "-100.00", "-40.25", rent),
        ("2025-12-29", "10.05", None, housing),
        ("2026-01-03", "-32.50", "-16.25", rent),
        ("2026-01-03", "4.25", None, rent),
        ("2026-01-03", "-8.00", None, None),
        ("2026-01-04", "-5.00", None, income),
        ("2026-01-05", "110.00", "55.00", income),
        ("2026-01-06", "-900.00", None, saving),
        ("2026-01-07", "-800.00", None, transfer),
        ("2026-01-08", "14.00", None, None),
        ("2026-02-02", "-3.47", None, rent),
        ("2026-02-02", "3.47", None, rent),
    ]:
        Expense.objects.create(
            user=owner,
            date=date.fromisoformat(day),
            amount=Decimal(amount),
            user_share=Decimal(share) if share is not None else None,
            category_obj=category,
        )
    Expense.objects.create(user=other, date=date(2026, 1, 3), amount=Decimal("-9876.54"))


def test_analytics_series_match_verified_migration_fixture(client, transactions):
    response = client.get(reverse("api:analytics"), {"month": "2026-01"})
    assert response.status_code == 200
    data = response.json()
    assert data["daily"] == [
        {"date": "2025-12-29", "daily": "30.20", "cumulative": "30.20"},
        {"date": "2026-01-03", "daily": "20.00", "cumulative": "50.20"},
        {"date": "2026-01-08", "daily": "14.00", "cumulative": "36.20"},
        {"date": "2026-02-02", "daily": "0.00", "cumulative": "36.20"},
    ]
    assert data["monthly"] == [
        {"month": "2025-12", "total_spent": "30.20"},
        {"month": "2026-01", "total_spent": "6.00"},
        {"month": "2026-02", "total_spent": "0.00"},
    ]
    assert data["category"] == {
        "month": "2026-01", "label": "January 2026", "previous": "2025-12", "next": "2026-02",
        "total": "18.00",
        "rows": [
            {"name": "Housing", "amount": "12.00", "percent": "66.67"},
            {"name": "Uncategorized", "amount": "6.00", "percent": "33.33"},
        ],
    }
    assert [(row["date"], row["income"], row["expenses"], row["balance"]) for row in data["cash_flow"]] == [
        ("2025-12-29", "0.00", "30.20", "-30.20"),
        ("2026-01-03", "0.00", "50.20", "-50.20"),
        ("2026-01-04", "-5.00", "50.20", "-55.20"),
        ("2026-01-05", "50.00", "50.20", "-0.20"),
        ("2026-01-08", "50.00", "36.20", "13.80"),
        ("2026-02-02", "50.00", "36.20", "13.80"),
    ]
    assert data["yearly"] == [
        {"year": 2025, "total_spent": "30.20"},
        {"year": 2026, "total_spent": "6.00"},
    ]


@pytest.mark.parametrize(
    ("month", "previous", "next_month", "rows"),
    [
        ("2026-02", "2026-01", "2026-03", [{"name": "Housing", "amount": "0.00", "percent": "0.00"}]),
        ("2026-03", "2026-02", "2026-04", []),
    ],
    ids=["zero-net-spending", "no-spending"],
)
def test_month_changes_only_category_and_preserves_zero_vs_empty(
    client, transactions, month, previous, next_month, rows
):
    url = reverse("api:analytics")
    january = client.get(url, {"month": "2026-01"}).json()
    selected = client.get(url, {"month": month}).json()
    category = selected.pop("category")
    january.pop("category")

    assert selected == january
    assert (category["month"], category["previous"], category["next"]) == (month, previous, next_month)
    assert (category["rows"], category["total"]) == (rows, "0.00")


def test_current_month_disables_next_and_invalid_month_falls_back(client, accounts):
    url = reverse("api:analytics")
    current = client.get(url).json()
    assert current == client.get(url, {"month": "bad-month"}).json()
    assert current["category"]["month"] == date.today().isoformat()[:7]
    assert current["category"]["next"] is None


def test_analytics_is_private_to_active_session(client, accounts, transactions):
    owner, other = accounts
    url = reverse("api:analytics")
    client.force_login(other)

    response = client.get(url, {"month": "2026-01"})
    assert response.json()["yearly"] == [{"year": 2026, "total_spent": "9876.54"}]
    assert "no-store" in response.headers["Cache-Control"]
    assert "Cookie" in response.headers["Vary"]
    assert client.get(url, headers={"X-Expense-Pilot-User": str(owner.pk)}).json()["code"] == "session_changed"
    assert client.post(url).status_code == 405

    client.logout()
    response = client.get(url)
    assert response.status_code == 401
    assert response.json()["code"] == "sign_in_required"


def test_analytics_without_allocations_returns_empty_series(client, accounts):
    data = client.get(reverse("api:analytics")).json()
    category = data.pop("category")
    assert data == {"daily": [], "monthly": [], "cash_flow": [], "yearly": []}
    assert (category["rows"], category["total"]) == ([], "0.00")


def test_zero_personal_share_counts_as_a_recorded_zero_in_all_groups(client, accounts):
    owner, _ = accounts
    Expense.objects.create(
        user=owner, date=date(2026, 2, 1), amount=Decimal("-25.00"), user_share=Decimal("0.00")
    )

    data = client.get(reverse("api:analytics"), {"month": "2026-02"}).json()
    assert data["daily"] == [{"date": "2026-02-01", "daily": "0.00", "cumulative": "0.00"}]
    assert data["monthly"] == [{"month": "2026-02", "total_spent": "0.00"}]
    assert data["category"]["rows"] == [{"name": "Uncategorized", "amount": "0.00", "percent": "0.00"}]
    assert data["cash_flow"] == [{"date": "2026-02-01", "income": "0.00", "expenses": "0.00", "balance": "0.00"}]
    assert data["yearly"] == [{"year": 2026, "total_spent": "0.00"}]


def test_analytics_route_preserves_month_on_sign_in(client, accounts):
    url = reverse("expenses_per_month")
    response = client.get(url, {"month": "2026-01"})
    assert response.status_code == 200
    assert response.context["app"]["screen"] == "analytics"
    assert response.context["app"]["analyticsApi"] == reverse("api:analytics")
    assert "no-store" in response.headers["Cache-Control"]

    client.logout()
    assert client.get(url, {"month": "2026-01"}).url == "/login/?next=/expenses/expenses-per-month/%3Fmonth%3D2026-01"
