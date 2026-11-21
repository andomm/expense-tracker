from datetime import date

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from .models import Category, Expense


@pytest.fixture
def make_expense(signed_in):
    def make(*, owner=signed_in, day=date.today(), amount="-1.00", **fields):
        return Expense.objects.create(user=owner, date=day, amount=amount, **fields)

    return make


@pytest.fixture
def signed_in(db, client):
    user = User.objects.create_user(username="pilot-reader")
    client.force_login(user)
    return user


def test_expense_list_opts_into_react_without_capturing_other_routes(
    signed_in, client, settings
):
    path = reverse("expense_list")
    settings.REACT_EXPENSES_PILOT = False
    assert client.get(path).templates[0].name == "expenses/expense_list.html"

    settings.DEBUG = True
    settings.REACT_EXPENSES_PILOT = True
    response = client.get(path, {"month": "all", "search": "fresh bread"})
    assert response.templates[0].name == "react_host.html"
    assert "no-store" in response.headers["Cache-Control"]
    assert "/@react-refresh" in response.content.decode()
    assert (
        client.get(reverse("category_list")).templates[0].name
        == "expenses/category_list.html"
    )
    assert client.get(reverse("admin:index")).url.startswith("/admin/login/")
    for path in (
        "/expenses/missing/",
        "/api/missing/",
        "/static/missing/",
        "/media/missing/",
    ):
        assert client.get(path).status_code == 404

    settings.DEBUG = False
    assert (
        client.get(reverse("expense_list")).templates[0].name
        == "expenses/expense_list.html"
    )


def test_session_read_and_protected_page_preserve_legacy_login(
    signed_in, client, settings
):
    settings.DEBUG = settings.REACT_EXPENSES_PILOT = True
    path = reverse("expense_list") + "?search=fresh%20bread"
    status_url = reverse("api:session")

    response = client.get(status_url)
    payload = response.json()
    assert payload["user"] == {"id": signed_in.pk, "username": "pilot-reader"}
    assert payload["csrf_token"] != client.cookies["csrftoken"].value
    assert "no-store" in response.headers["Cache-Control"]
    assert "Cookie" in response.headers["Vary"]
    assert client.post(status_url).status_code == 405

    client.logout()
    assert client.get(status_url).json()["user"] is None
    assert client.get(path).url == "/login/?next=/expenses/%3Fsearch%3Dfresh%2520bread"


def test_pages_have_stable_ids_but_summary_and_top_cover_all_rows(
    signed_in, client, make_expense
):
    same_day = date(2026, 5, 2)
    tied = [make_expense(day=same_day).pk for _ in range(51)]
    largest = make_expense(day=date(2026, 5, 1), amount="-100.50", user_share="-50.25")
    make_expense(
        day=same_day, amount="5.25"
    )  # Uncategorized refund reduces net spending.
    second_largest = make_expense(day=same_day, amount="-3.20")
    for kind, amount in [
        ("income", "200.10"),
        ("saving", "-10.05"),
        ("transfer", "-999.00"),
    ]:
        category = Category.objects.create(
            user=signed_in, name=kind, category_type=kind
        )
        make_expense(day=same_day, amount=amount, category_obj=category)
    make_expense(
        day=same_day, amount="0.00"
    )  # Zero-source rows are hidden in legacy too.

    url = reverse("api:expenses")
    response = client.get(url, {"month": "all"})
    first = response.json()
    second = client.get(url, {"month": "all", "page": 2}).json()
    assert "no-store" in response.headers["Cache-Control"]
    assert first["pagination"] == {"page": 1, "page_size": 50, "pages": 2, "count": 57}
    assert [row["id"] for row in first["rows"]] == tied[:50]
    assert second["rows"][0]["id"] == tied[-1]
    assert second["rows"][-1]["id"] == largest.pk
    assert second["rows"][-1]["amount"] == "-100.50"
    assert second["rows"][-1]["personal_share"] == "-50.25"
    assert (
        first["summary"]
        == second["summary"]
        == {
            "total_spent": "-99.20",
            "income": "200.10",
            "savings_total": "10.05",
            "balance": "100.90",
        }
    )
    top_ids = [largest.pk, second_largest.pk, *tied[:3]]
    assert [row["id"] for row in first["top_expenses"]] == top_ids
    assert first["top_expenses"] == second["top_expenses"]

    legacy = client.get(reverse("expense_list"), {"month": "all"}).context
    assert {key: f"{legacy[key]:.2f}" for key in first["summary"]} == first["summary"]
    assert [row.expense.pk for row in legacy["top_expenses"]] == top_ids


@pytest.mark.parametrize(
    "order_by,expected",
    [
        ("date", "cab"),
        ("-date", "abc"),
        ("amount", "bac"),
        ("-amount", "cab"),
        ("category_obj__name", "bca"),
        ("-category_obj__name", "acb"),
        ("receiver", "acb"),
        ("-receiver", "bca"),
    ],
)
def test_sort_order_uses_full_amount_and_stored_fields(
    signed_in, client, make_expense, order_by, expected
):
    rows = {}
    for key, day, amount, share, receiver, category in [
        ("a", 2, "-20.00", "-15.00", "Apple", "Transit"),
        ("b", 2, "-30.00", "-1.00", "Zebra", "Books"),
        ("c", 1, "-10.00", "-10.00", "Fox", "Rent"),
    ]:
        cat = Category.objects.create(user=signed_in, name=category)
        rows[key] = make_expense(
            day=date(2025, 6, day),
            amount=amount,
            user_share=share,
            receiver=receiver,
            category_obj=cat,
        ).pk
    result = client.get(
        reverse("api:expenses"), {"month": "all", "order_by": order_by}
    ).json()
    assert [row["id"] for row in result["rows"]] == [rows[key] for key in expected]


@pytest.mark.parametrize(
    "filters,keys",
    [
        ({}, "d"),
        ({"month": "specific"}, "abc"),
        ({"month": "all", "category_filter": "root"}, "ab"),
        ({"month": "all", "category_filter": "uncategorized"}, "dc"),
        ({"month": "all", "search": " PApEr "}, "a"),
        ({"month": "all", "search": "binding"}, "b"),
        ({"month": "all", "search": "stored"}, "b"),
        ({"month": "all", "search": "journals"}, "b"),
    ],
)
def test_date_category_and_search_filters(
    signed_in, client, make_expense, filters, keys
):
    current = date.today().replace(day=1)
    prior = current.replace(year=current.year - 1)
    root = Category.objects.create(user=signed_in, name="Bookshelf")
    child = Category.objects.create(user=signed_in, name="Journals", parent=root)
    rows = {
        "a": make_expense(day=prior, category_obj=root, receiver="Paper store").pk,
        "b": make_expense(
            day=prior,
            category_obj=child,
            category="Stored category",
            description="Book binding",
        ).pk,
        "c": make_expense(day=prior, receiver="Miscellaneous").pk,
        "d": make_expense(day=current, receiver="Groceries").pk,
    }
    params = {**filters}
    if params.get("month") == "specific":
        params["month"] = prior.isoformat()[:7]
    if params.get("category_filter") == "root":
        params["category_filter"] = root.pk
    result = client.get(reverse("api:expenses"), params).json()
    assert [row["id"] for row in result["rows"]] == [rows[key] for key in keys]
    assert result["months"]["current"] == current.isoformat()[:7]
    assert result["months"]["min_year"] == prior.year
    assert result["filters"]["month"] == params.get("month", current.isoformat()[:7])
    if "search" in params:
        assert result["filters"]["search"] == params["search"].strip()


def test_rows_totals_picker_and_category_choices_are_account_scoped(
    signed_in, client, make_expense
):
    other = User.objects.create_user(username="another-reader")
    foreign_category = Category.objects.create(user=other, name="Private label")
    foreign = make_expense(
        owner=other,
        day=date(2000, 1, 1),
        amount="-222.00",
        category_obj=foreign_category,
    )
    own = make_expense(
        category_obj=foreign_category
    )  # Even an inconsistent link cannot expose the label.

    url = reverse("api:expenses")
    own_result = client.get(
        url, {"month": "all", "category_filter": foreign_category.pk}
    ).json()
    assert [row["id"] for row in own_result["rows"]] == [own.pk]
    assert own_result["rows"][0]["category"] is None
    assert own_result["summary"]["total_spent"] == "-1.00"
    assert own_result["months"]["min_year"] == date.today().year
    assert "Private label" not in [
        choice["label"] for choice in own_result["categories"]
    ]
    assert client.get(url, {"search": "Private label"}).json()["rows"] == []

    client.force_login(other)
    other_result = client.get(url, {"month": "all"}).json()
    assert [row["id"] for row in other_result["rows"]] == [foreign.pk]
    assert other_result["summary"]["total_spent"] == "-222.00"


def test_legacy_logout_requires_csrf_and_protected_api_returns_json_afterwards(
    signed_in,
):
    client = Client(enforce_csrf_checks=True)
    client.force_login(signed_in)
    session = client.get(reverse("api:session")).json()
    logout = reverse("logout")
    expenses = reverse("api:expenses")
    assert client.get(logout).status_code == 405
    assert client.post(logout).status_code == 403
    assert (
        client.post(
            reverse("api:session"), {"csrfmiddlewaretoken": session["csrf_token"]}
        ).json()[
            "code"
        ]
        == "method_not_allowed"
    )
    assert client.post(
        logout, {"csrfmiddlewaretoken": session["csrf_token"]}
    ).url == reverse("login")
    response = client.get(expenses)
    assert response.status_code == 401
    assert response.json()["code"] == "sign_in_required"
    assert "no-store" in response.headers["Cache-Control"]


def test_filtered_pilot_link_keeps_search_when_served_by_legacy(
    signed_in, client, settings, make_expense
):
    settings.REACT_EXPENSES_PILOT = False
    match = make_expense(receiver="Corner shop")
    make_expense(receiver="Other store")
    response = client.get(
        reverse("expense_list"),
        {
            "month": "all",
            "category_filter": "all",
            "search": "corner",
            "order_by": "receiver",
        },
    )
    assert [row.expense.pk for row in response.context["expense_rows"]] == [match.pk]


def test_invalid_page_is_json_error_and_empty_list_is_success(signed_in, client):
    url = reverse("api:expenses")
    response = client.get(url, {"page": "not-a-number"})
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_page"
    result = client.get(url, {"page": 2}).json()
    assert result["pagination"] == {"page": 1, "page_size": 50, "pages": 1, "count": 0}
    assert result["rows"] == result["top_expenses"] == []
    assert result["summary"]["balance"] == "0.00"
