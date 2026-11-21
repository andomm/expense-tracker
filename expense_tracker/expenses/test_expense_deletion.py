from datetime import date

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from .models import Expense

JSON = "application/json"
FILTERS = {
    "month": "2026-03",
    "search": "market",
    "category_filter": "uncategorized",
    "order_by": "amount",
}


def signed_in(user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    client.defaults["HTTP_X_CSRFTOKEN"] = client.get(reverse("api:session")).json()[
        "csrf_token"
    ]
    return client


@pytest.fixture
def ledger(db):
    owner = User.objects.create_user(username="delete-owner")
    other = User.objects.create_user(username="delete-neighbor")

    def expense(user, day, amount):
        return Expense.objects.create(
            user=user, date=day, amount=amount, receiver="Market"
        ).pk

    target = expense(owner, date(2026, 3, 12), "-12.35")
    sibling = expense(owner, date(2026, 3, 10), "-4.70")
    outside = expense(owner, date(2026, 2, 10), "-30.00")
    foreign = expense(other, date(2026, 3, 12), "-19.99")
    return signed_in(owner), signed_in(other), target, sibling, outside, foreign


def filtered_rows(client):
    return client.get(reverse("api:expenses"), FILTERS).json()


def test_delete_one_only_removes_selected_record_and_refreshes_exact_totals(ledger):
    owner, other, target, sibling, outside, foreign = ledger
    detail = reverse("api:expense-detail", args=[target])
    assert owner.get(detail).json()["receiver"] == "Market"
    assert filtered_rows(owner)["summary"]["balance"] == "-17.05"

    response = owner.delete(detail)
    assert response.status_code == 200
    assert response.json() == {"deleted_count": 1}
    assert owner.get(detail).status_code == 404
    assert owner.get(reverse("api:expense-detail", args=[outside])).status_code == 200
    assert other.get(reverse("api:expense-detail", args=[foreign])).status_code == 200
    result = filtered_rows(owner)
    assert [row["id"] for row in result["rows"]] == [sibling]
    assert result["summary"]["balance"] == "-4.70"
    assert owner.delete(detail).status_code == 404


def test_delete_all_preview_ignores_filters_and_post_deletes_only_account(ledger):
    owner, other, _, _, _, foreign = ledger
    action = reverse("api:expense-delete-all")
    assert filtered_rows(owner)["pagination"]["count"] == 2
    assert owner.get(action, FILTERS).json() == {"count": 3}

    response = owner.post(f"{action}?month=2026-03", {"confirmation": "DELETE"}, JSON)
    assert response.status_code == 200
    assert response.json() == {"deleted_count": 3}
    assert owner.get(action).json() == {"count": 0}
    result = filtered_rows(owner)
    assert result["rows"] == result["top_expenses"] == []
    assert result["summary"] == dict.fromkeys(
        ("balance", "total_spent", "income", "savings_total"), "0.00"
    )
    assert [row["id"] for row in filtered_rows(other)["rows"]] == [foreign]


@pytest.mark.parametrize(
    "body", [{}, {"confirmation": "delete"}, {"confirmation": "DELETE "}]
)
def test_delete_all_rejects_nonliteral_confirmation(ledger, body):
    owner, _, _, _, _, _ = ledger
    action = reverse("api:expense-delete-all")
    response = owner.post(action, body, JSON)
    assert response.status_code == 422
    assert owner.get(action).json() == {"count": 3}


@pytest.mark.parametrize("all_expenses", [False, True], ids=["single", "account-wide"])
def test_delete_writes_require_csrf_and_the_expected_session(ledger, all_expenses):
    owner, _, target, _, _, _ = ledger
    if all_expenses:
        url = reverse("api:expense-delete-all")

        def write(client, **headers):
            return client.post(url, {"confirmation": "DELETE"}, JSON, **headers)
    else:
        url = reverse("api:expense-detail", args=[target])

        def write(client, **headers):
            return client.delete(url, **headers)

    rejected = write(owner, HTTP_X_CSRFTOKEN="")
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "csrf_failed"
    assert write(owner, HTTP_X_EXPENSE_PILOT_USER="0").status_code == 401

    # A valid CSRF cookie/token pair can outlive the authenticated session.
    del owner.cookies["sessionid"]
    assert owner.get(url).status_code == 401
    assert write(owner).status_code == 401
    assert Expense.objects.count() == 4


def test_single_delete_cannot_target_another_accounts_expense(ledger):
    owner, other, _, _, _, foreign = ledger
    foreign_url = reverse("api:expense-detail", args=[foreign])
    missing_url = reverse("api:expense-detail", args=[0])
    forbidden = owner.delete(foreign_url)
    missing = owner.delete(missing_url)
    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.json() == missing.json()
    assert other.get(foreign_url).status_code == 200


def test_legacy_delete_all_still_requires_typed_confirmation(ledger, settings):
    settings.DEBUG = settings.LOCAL_REACT_DEV = settings.LEGACY_PAGES = True
    owner, other, _, _, _, foreign = ledger
    page = reverse("expense_delete_all")
    assert owner.get(page).context["count"] == 3
    assert owner.post(page, {"confirmation": " DELETE"}).status_code == 422
    assert owner.get(reverse("api:expense-delete-all")).json() == {"count": 3}
    assert owner.post(page, {"confirmation": "DELETE"}).url == reverse("expense_list")
    assert owner.get(reverse("api:expense-delete-all")).json() == {"count": 0}
    assert other.get(reverse("api:expense-detail", args=[foreign])).status_code == 200


@pytest.mark.parametrize("all_expenses", [False, True], ids=["single", "account-wide"])
def test_react_confirmation_urls_are_read_only_and_keep_local_filters(
    ledger, settings, all_expenses
):
    settings.DEBUG = settings.LOCAL_REACT_DEV = True
    settings.LEGACY_PAGES = False
    owner, _, target, _, _, foreign = ledger
    name = "expense_delete_all" if all_expenses else "expense_delete"
    url = reverse(name, args=[] if all_expenses else [target])
    response = owner.get(url, {**FILTERS, "page": "2", "next": "//evil.example"})
    assert response.templates[0].name == "react_host.html"
    routes = response.context["app"]["deletion"]
    assert routes["returnUrl"] == (
        f"{reverse('expense_list')}?month=2026-03&order_by=amount&"
        "category_filter=uncategorized&search=market&page=2"
    )
    assert owner.post(url, {"confirmation": "DELETE"}).status_code == 405
    assert Expense.objects.count() == 4
    if not all_expenses:
        assert owner.get(reverse(name, args=[foreign])).status_code == 404
