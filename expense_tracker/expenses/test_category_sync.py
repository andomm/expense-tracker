from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from .models import Category, Expense

START = "/api/categories/sync/"
LATEST = "/api/categories/sync/latest-result/"


@pytest.fixture
def sync_accounts(db):
    users = [User.objects.create_user(name) for name in ("sync-owner", "other-owner")]
    Category.objects.filter(user__in=users).delete()
    clients = [Client(enforce_csrf_checks=True) for _ in users]
    for client, user in zip(clients, users, strict=True):
        client.force_login(user)
    return (*users, *clients)


@pytest.fixture
def expense(sync_accounts):
    def make(*, owner=sync_accounts[0], **fields):
        return Expense.objects.create(
            user=owner,
            date=date(2024, 3, 2),
            amount="-17.25",
            user_share="-8.50",
            **fields,
        )

    return make


def post_sync(client, *, data=None):
    token = client.get(reverse("api:session")).json()["csrf_token"]
    return client.post(
        START,
        {} if data is None else data,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )


def test_explicit_sync_keeps_source_priority_and_only_upgrades_within_the_same_root(
    sync_accounts, expense
):
    owner, other, client, other_client = sync_accounts
    food = Category.objects.create(user=owner, name="Food", keywords="market")
    groceries = Category.objects.create(user=owner, name="Groceries", parent=food)
    drinks = Category.objects.create(user=owner, name="Drinks", parent=food)
    bakery = Category.objects.create(
        user=owner, name="Bakery", parent=groceries, keywords="bread"
    )
    travel = Category.objects.create(user=owner, name="Travel")
    Category.objects.create(user=owner, name="Metro", parent=travel, keywords="metro")
    Category.objects.create(
        user=other, name="Private", keywords="private fixture, bread"
    )
    assigned = expense(receiver="THE MARKET", description="metro")
    upgraded = expense(
        description="Fresh Bread", category_obj=drinks, category=drinks.name
    )
    unmatched = expense(receiver="private fixture")
    wrong_root = expense(receiver="metro", category_obj=food, category=food.name)
    not_deeper = expense(receiver="market", category_obj=bakery, category=bakery.name)
    foreign = expense(
        owner=other, receiver="private fixture", description="Other user's row"
    )

    assert client.get(START).status_code == 405
    response = post_sync(client)
    assert response.status_code == 200, response.content
    counts = {
        "uncategorized_before": 2,
        "newly_categorized": 1,
        "upgraded": 1,
        "still_uncategorized": 1,
    }
    result_url = reverse("sync_summary")
    assert response.json()["result_id"]
    assert response.json()["result_url"] == result_url
    assert response.json()["counts"] == counts
    result = client.get(LATEST).json()["result"]
    assert result["id"] == response.json()["result_id"]
    assert result["counts"] == counts
    for group, row, details in (
        (
            "newly_categorized",
            assigned,
            {
                "category": "Food",
                "matched_keyword": "market",
                "matched_from": "receiver",
            },
        ),
        (
            "upgraded",
            upgraded,
            {
                "old_category": "Drinks",
                "new_category": "Bakery",
                "matched_keyword": "bread",
                "matched_from": "description",
            },
        ),
        ("still_uncategorized", unmatched, {}),
    ):
        assert result["previews"][group] == {
            "omitted": 0,
            "rows": [
                {
                    "id": row.pk,
                    "edit_url": reverse("expense_edit", args=[row.pk]),
                    "date": "2024-03-02",
                    "receiver": row.receiver,
                    "description": row.description,
                    "amount": "-17.25",
                    **details,
                }
            ],
        }
        assert (
            other_client.get(reverse("expense_edit", args=[row.pk])).status_code == 404
        )
    for row, category in (
        (assigned, food),
        (upgraded, bakery),
        (unmatched, None),
        (wrong_root, food),
        (not_deeper, bakery),
        (foreign, None),
    ):
        row.refresh_from_db()
        assert row.category_obj == category
        assert row.category == (category.name if category else "")
        assert row.amount == Decimal("-17.25") and row.user_share == Decimal("-8.50")


def test_latest_result_is_read_only_and_lives_only_in_the_same_session(
    sync_accounts, expense
):
    owner, _, client, other_client = sync_accounts
    food = Category.objects.create(user=owner, name="Food", keywords="market")
    assert client.get(LATEST).json() == {"result": None}

    first = post_sync(client).json()
    assert first["counts"] == dict.fromkeys(
        (
            "uncategorized_before",
            "newly_categorized",
            "upgraded",
            "still_uncategorized",
        ),
        0,
    )
    new = expense(receiver="Market")
    for _ in range(2):
        response = client.get(LATEST)
        assert "no-store" in response.headers["Cache-Control"]
        assert "Cookie" in response.headers["Vary"]
        assert response.json()["result"]["id"] == first["result_id"]
        assert response.json()["result"]["counts"] == first["counts"]
    new.refresh_from_db()
    assert new.category_obj is None

    same_user_elsewhere = Client(enforce_csrf_checks=True)
    same_user_elsewhere.force_login(owner)
    assert (
        same_user_elsewhere.get(LATEST).json()
        == other_client.get(LATEST).json()
        == {"result": None}
    )

    second = post_sync(client).json()
    assert second["result_id"] != first["result_id"]
    assert second["counts"]["newly_categorized"] == 1
    new.refresh_from_db()
    assert new.category_obj == food
    latest = client.get(LATEST).json()["result"]
    assert latest["id"] == second["result_id"]
    assert latest["previews"]["newly_categorized"]["rows"][0]["id"] == new.pk
    new.delete()
    assert (
        client.get(LATEST).json()["result"]["previews"]["newly_categorized"]["rows"][0][
            "edit_url"
        ]
        is None
    )

    client.logout()
    assert client.get(LATEST).status_code == 401
    client.force_login(owner)
    assert client.get(LATEST).json() == {"result": None}


def test_rejected_sync_does_not_apply_changes_or_replace_latest(sync_accounts, expense):
    owner, other, client, _ = sync_accounts
    Category.objects.create(user=owner, name="Food", keywords="market")
    first_id = post_sync(client).json()["result_id"]
    pending = expense(receiver="Market")
    token = client.get(reverse("api:session")).json()["csrf_token"]
    json_post = {"content_type": "application/json"}
    csrf = {"HTTP_X_CSRFTOKEN": token}

    missing_token = client.post(START, {}, **json_post)
    assert (
        missing_token.status_code == 403
        and missing_token.json()["code"] == "csrf_failed"
    )
    assert post_sync(client, data={"user_id": other.pk}).status_code == 400
    assert client.post(LATEST, {}, **json_post, **csrf).status_code == 405
    for method, path in (("get", LATEST), ("post", START)):
        response = getattr(client, method)(
            path, HTTP_X_EXPENSE_PILOT_USER=str(other.pk), **csrf
        )
        assert (
            response.status_code == 401 and response.json()["code"] == "session_changed"
        )
    assert client.get(LATEST).json()["result"]["id"] == first_id

    client.session.delete()
    assert client.get(LATEST).status_code == 401
    assert client.post(START, {}, **json_post, **csrf).status_code == 401
    pending.refresh_from_db()
    assert pending.category_obj is None


def test_preview_limits_never_limit_writes_or_counts(sync_accounts, expense):
    owner, _, client, _ = sync_accounts
    root = Category.objects.create(user=owner, name="Food", keywords="market")
    child = Category.objects.create(
        user=owner, name="Bakery", keywords="bread", parent=root
    )
    for _ in range(51):
        assigned = expense(receiver="Market")
        upgraded = expense(receiver="Bread", category_obj=root, category=root.name)
        unmatched = expense(receiver="Unknown")

    assert post_sync(client).json()["counts"] == {
        "uncategorized_before": 102,
        "newly_categorized": 51,
        "upgraded": 51,
        "still_uncategorized": 51,
    }
    previews = client.get(LATEST).json()["result"]["previews"]
    for key, last, category in (
        ("newly_categorized", assigned, root),
        ("upgraded", upgraded, child),
        ("still_uncategorized", unmatched, None),
    ):
        assert previews[key]["omitted"] == 1
        assert len(previews[key]["rows"]) == 50
        assert last.pk not in {row["id"] for row in previews[key]["rows"]}
        last.refresh_from_db()
        assert last.category_obj == category


def test_retained_sync_form_redirects_to_legacy_report(
    sync_accounts, expense, settings
):
    owner, _, client, _ = sync_accounts
    settings.DEBUG = settings.LOCAL_REACT_DEV = settings.LEGACY_PAGES = True
    Category.objects.create(user=owner, name="Groceries", keywords="market")
    row = expense(receiver="Market")
    categories = client.get(reverse("category_list"))
    start = reverse("sync_categories")
    result = reverse("sync_summary")
    assert client.get(start).url == reverse("category_list")
    assert f'action="{start}"' in categories.content.decode()
    assert client.post(start).status_code == 403
    token = client.get(reverse("api:session")).json()["csrf_token"]
    assert client.post(start, {"csrfmiddlewaretoken": token}).url == result
    response = client.get(result)
    assert response.templates[0].name == "expenses/sync_summary.html"
    assert "Groceries" in response.content.decode()
    assert reverse("expense_edit", args=[row.pk]) in response.content.decode()
    assert client.get(LATEST).json()["result"]["counts"]["newly_categorized"] == 1


@pytest.mark.parametrize(
    ("local", "debug", "legacy", "react"),
    [
        (True, True, False, True),
        (True, True, True, False),
        (False, True, False, False),
        (True, False, False, False),
    ],
    ids=["default", "fallback", "plain-django", "debug-disabled"],
)
def test_sync_pages_move_together(sync_accounts, settings, local, debug, legacy, react):
    _, _, client, _ = sync_accounts
    settings.LOCAL_REACT_DEV = local
    settings.DEBUG = debug
    settings.LEGACY_PAGES = legacy
    start = client.get(reverse("sync_categories"))
    summary = client.get(reverse("sync_summary"))
    if react:
        for response, screen in (
            (start, "category-sync"),
            (summary, "category-sync-result"),
        ):
            assert response.templates[0].name == "react_host.html"
            assert response.context["app"]["screen"] == screen
            assert "no-store" in response.headers["Cache-Control"]
        token = client.get(reverse("api:session")).json()["csrf_token"]
        assert (
            client.post(
                reverse("sync_categories"), {"csrfmiddlewaretoken": token}
            ).status_code
            == 405
        )
        assert client.get(LATEST).json() == {"result": None}
    else:
        assert start.url == reverse("category_list")
        assert summary.templates[0].name == "expenses/sync_summary.html"
