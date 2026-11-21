import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.db.models.signals import pre_save
from django.test import Client
from django.urls import reverse

from .models import Category, Expense, ExpenseSplitRule

JSON = "application/json"


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="expense-writer")


@pytest.fixture
def writer(owner):
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    token = client.get(reverse("api:session")).json()["csrf_token"]
    client.defaults["HTTP_X_CSRFTOKEN"] = token
    return client


@pytest.fixture
def other(db):
    return User.objects.create_user(username="another-writer")


@pytest.fixture
def category(owner):
    return Category.objects.create(user=owner, name="Market")


@pytest.fixture
def payload(category):
    return {
        "date": "2026-03-09",
        "receiver": "Corner shop",
        "description": "Weekly shop",
        "amount": "-100.00",
        "category_id": category.pk,
        "share_rule_id": None,
        "splits": [],
    }


def test_full_split_replaces_edit_source_with_independent_shared_expenses(
    writer, owner, payload, category
):
    second = Category.objects.create(user=owner, name="Hardware")
    rule = ExpenseSplitRule.objects.create(
        user=owner, name="Household", split_percentage="50"
    )
    listing = reverse("api:expenses")
    created = writer.post(listing, payload, content_type=JSON)
    assert created.status_code == 201
    source = created.json()["retained_id"]
    detail = reverse("api:expense-detail", args=[source])
    split = writer.put(
        detail,
        {
            **payload,
            "category_id": None,
            "share_rule_id": rule.pk,
            "splits": [
                {"amount": "30.00", "category_id": category.pk},
                {"amount": "70.00", "category_id": second.pk},
            ],
        },
        content_type=JSON,
    )
    assert split.status_code == 200
    first_id, second_id = split.json()["expense_ids"]
    assert split.json()["retained_id"] is None
    assert writer.get(detail).status_code == 404

    reread = writer.get(listing, {"month": "all"}).json()
    assert [
        (row["id"], row["amount"], row["personal_share"]) for row in reread["rows"]
    ] == [
        (first_id, "-30.00", "-15.00"),
        (second_id, "-70.00", "-35.00"),
    ]
    assert reread["summary"]["balance"] == "-50.00"

    first_detail = reverse("api:expense-detail", args=[first_id])
    assert writer.put(
        first_detail,
        {
            **payload,
            "amount": "-30.00",
            "share_rule_id": rule.pk,
            "receiver": "Renamed shop",
        },
        content_type=JSON,
    ).json() == {"expense_ids": [first_id], "retained_id": first_id}
    assert writer.get(first_detail).json()["receiver"] == "Renamed shop"
    assert (
        writer.get(reverse("api:expense-detail", args=[second_id])).json()["receiver"]
        == "Corner shop"
    )


def test_partial_split_preview_and_save_keep_positive_sign_and_main_category(
    writer, owner, payload
):
    part = Category.objects.create(user=owner, name="Gift refund")
    rule = ExpenseSplitRule.objects.create(
        user=owner, name="25 percent", split_percentage="25"
    )
    listing = reverse("api:expenses")
    source = writer.post(listing, payload, content_type=JSON).json()["retained_id"]
    data = {
        **payload,
        "amount": "100.00",
        "share_rule_id": rule.pk,
        "splits": [{"amount": "30.00", "category_id": part.pk}],
    }
    preview = writer.post(
        reverse("api:expense-preview", args=[source]), data, content_type=JSON
    )
    assert preview.json() == {
        "amount": "100.00",
        "split_total": "30.00",
        "remaining": "70.00",
        "personal_share": "25.00",
    }
    before = writer.get(listing, {"month": "all"}).json()["rows"]
    assert [(item["id"], item["amount"]) for item in before] == [(source, "-100.00")]

    detail = reverse("api:expense-detail", args=[source])
    saved = writer.put(detail, data, content_type=JSON).json()
    assert saved["retained_id"] == source
    remainder, split = [
        writer.get(reverse("api:expense-detail", args=[pk])).json()
        for pk in saved["expense_ids"]
    ]
    assert (
        remainder["id"],
        remainder["category_id"],
        remainder["amount"],
        remainder["personal_share"],
    ) == (
        source,
        payload["category_id"],
        "70.00",
        "17.50",
    )
    assert (split["category_id"], split["amount"], split["personal_share"]) == (
        part.pk,
        "30.00",
        "7.50",
    )


@pytest.mark.parametrize(
    "failure,path",
    [
        ("blank row", "splits[0].amount"),
        ("nonpositive part", "splits[0].amount"),
        ("part precision", "splits[0].amount"),
        ("over total", "splits"),
        ("no remainder category", "category_id"),
        ("full amount precision", "amount"),
    ],
)
def test_invalid_edit_reports_field_paths_without_changing_list(
    writer, payload, failure, path
):
    listing = reverse("api:expenses")
    listing_params = {"month": "all"}
    pk = writer.post(listing, payload, content_type=JSON).json()["retained_id"]
    baseline = writer.get(listing, listing_params).json()
    edited = {**payload, "receiver": "Should not save"}
    part = {"category_id": payload["category_id"], "amount": "30.00"}
    edited["splits"] = [part]
    if failure == "blank row":
        edited["splits"] = [{}]
    elif failure == "nonpositive part":
        part["amount"] = "0.00"
    elif failure == "part precision":
        part["amount"] = "30.001"
    elif failure == "over total":
        part["amount"] = "100.01"
    elif failure == "no remainder category":
        edited["category_id"] = None
    else:
        edited["amount"] = "-99.001"

    response = writer.put(
        reverse("api:expense-detail", args=[pk]), edited, content_type=JSON
    )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    assert path in response.json()["fields"]
    assert writer.get(listing, listing_params).json() == baseline


def test_foreign_expenses_and_choices_are_scoped(
    writer, owner, other, payload, category
):
    foreign = Category.objects.create(user=other, name="Private category")
    own_rule = ExpenseSplitRule.objects.create(
        user=owner, name="Shared", split_percentage="50"
    )
    other_rule = ExpenseSplitRule.objects.create(
        user=other, name="Private share", split_percentage="50"
    )
    expense = Expense.objects.create(
        user=other, date=payload["date"], amount="-5.00", category_obj=foreign
    )
    detail = reverse("api:expense-detail", args=[expense.pk])
    get = writer.get(detail)
    put = writer.put(detail, payload, content_type=JSON)
    assert get.status_code == put.status_code == 404
    assert get.json() == put.json()
    preview = writer.post(
        reverse("api:expense-preview", args=[expense.pk]), payload, content_type=JSON
    )
    assert preview.status_code == 404
    assert preview.json() == get.json()
    options = writer.get(reverse("api:expense-form-options")).json()
    assert category.pk in {choice["id"] for choice in options["categories"]}
    assert foreign.pk not in {choice["id"] for choice in options["categories"]}
    assert options["share_rules"] == [{"id": own_rule.pk, "label": "Shared (50.00%)"}]

    listing = reverse("api:expenses")
    invalid = {
        **payload,
        "category_id": foreign.pk,
        "share_rule_id": other_rule.pk,
        "splits": [{"category_id": foreign.pk, "amount": "30.00"}],
    }
    response = writer.post(listing, invalid, content_type=JSON)
    assert response.status_code == 422
    assert set(response.json()["fields"]) == {
        "category_id",
        "share_rule_id",
        "splits[0].category_id",
    }
    nonexistent = 999999
    invalid.update(category_id=nonexistent, share_rule_id=nonexistent)
    invalid["splits"][0]["category_id"] = nonexistent
    assert writer.post(listing, invalid, content_type=JSON).json() == response.json()
    assert writer.get(listing, {"month": "all"}).json()["rows"] == []


@pytest.mark.parametrize(
    "start_with_rule,stored_share", [(True, "-50.00"), (False, "-100.00")]
)
def test_edit_without_rule_preserves_legacy_stored_share(
    writer, owner, payload, start_with_rule, stored_share
):
    rule = ExpenseSplitRule.objects.create(
        user=owner, name="Half share", split_percentage="50"
    )
    created = writer.post(
        reverse("api:expenses"),
        {
            **payload,
            "share_rule_id": rule.pk if start_with_rule else None,
        },
        content_type=JSON,
    )
    detail = reverse("api:expense-detail", args=[created.json()["retained_id"]])
    edited = {**payload, "amount": "-80.00"}
    preview = writer.post(
        reverse("api:expense-preview", args=[created.json()["retained_id"]]),
        edited,
        content_type=JSON,
    )
    assert preview.json()["personal_share"] == stored_share
    assert writer.put(detail, edited, content_type=JSON).status_code == 200
    received = writer.get(detail).json()
    assert (
        received["amount"],
        received["share_rule_id"],
        received["personal_share"],
    ) == (
        "-80.00",
        None,
        stored_share,
    )


def test_split_preview_adds_rounded_shares_for_independent_rows(writer, owner, payload):
    rule = ExpenseSplitRule.objects.create(
        user=owner, name="Half share", split_percentage="50"
    )
    data = {
        **payload,
        "amount": "-0.06",
        "share_rule_id": rule.pk,
        "splits": [{"amount": "0.03", "category_id": payload["category_id"]}] * 2,
    }
    preview = writer.post(reverse("api:expense-preview"), data, content_type=JSON)
    assert preview.json()["personal_share"] == "-0.04"
    listing = reverse("api:expenses")
    assert writer.post(listing, data, content_type=JSON).status_code == 201
    assert writer.get(listing, {"month": "all"}).json()["summary"]["balance"] == "-0.04"


def test_write_rejects_bad_csrf_malformed_json_and_missing_session(writer, payload):
    url = reverse("api:expenses")
    rejected = writer.post(url, payload, content_type=JSON, HTTP_X_CSRFTOKEN="")
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "csrf_failed"
    assert "no-store" in rejected.headers["Cache-Control"]
    malformed = writer.post(url, "[not-json", content_type=JSON)
    assert malformed.status_code == 400
    assert malformed.json()["code"] == "invalid_request"
    assert writer.get(url, {"month": "all"}).json()["rows"] == []
    del writer.cookies[
        "sessionid"
    ]  # Keep the valid CSRF token; expire just the session.
    expired = writer.post(url, payload, content_type=JSON)
    assert expired.status_code == 401
    assert expired.json()["code"] == "sign_in_required"


def test_stale_pilot_form_cannot_read_or_save_under_another_session(
    writer, payload, other
):
    detail = reverse(
        "api:expense-detail",
        args=[
            Expense.objects.create(
                user=other, date=payload["date"], amount="-20.00"
            ).pk,
        ],
    )
    old_user = writer.get(reverse("api:session")).json()["user"]["id"]
    writer.force_login(other)
    session = writer.get(reverse("api:session")).json()
    listing = reverse("api:expenses")
    options_url = reverse("api:expense-form-options")
    baseline = writer.get(listing, {"month": "all"}).json()
    headers = {
        "HTTP_X_EXPENSE_PILOT_USER": str(old_user),
        "HTTP_X_CSRFTOKEN": session["csrf_token"],
    }

    replies = [
        writer.get(options_url, **headers),
        writer.get(detail, **headers),
        writer.post(
            listing, {**payload, "category_id": None}, content_type=JSON, **headers
        ),
    ]
    for response in replies:
        assert response.status_code == 401
        assert response.json()["code"] == "session_changed"
    assert writer.get(listing, {"month": "all"}).json() == baseline


def test_storage_failure_rolls_back_remainder_and_earlier_parts(writer, payload):
    url = reverse("api:expenses")
    pk = writer.post(url, payload, content_type=JSON).json()["retained_id"]
    edited = {
        **payload,
        "splits": [
            {"category_id": payload["category_id"], "amount": "10.00"},
            {"category_id": payload["category_id"], "amount": "20.00"},
        ],
    }

    def reject_second_part(sender, instance, **kwargs):
        if instance.pk is None and instance.amount == -20:
            raise IntegrityError("synthetic failure during second split insert")

    with pytest.raises(IntegrityError, match="second split insert"):
        pre_save.connect(reject_second_part, sender=Expense)
        try:
            writer.put(
                reverse("api:expense-detail", args=[pk]), edited, content_type=JSON
            )
        finally:
            pre_save.disconnect(reject_second_part, sender=Expense)

    rows = writer.get(url, {"month": "all"}).json()["rows"]
    assert [(item["id"], item["amount"]) for item in rows] == [(pk, "-100.00")]


def test_add_and_edit_routes_opt_in_without_swallowing_legacy_or_foreign_pages(
    writer, owner, other, settings
):
    own = Expense.objects.create(user=owner, date="2026-01-01", amount="-1.00")
    foreign = Expense.objects.create(user=other, date="2026-01-01", amount="-2.00")
    routes = (reverse("expense_add"), reverse("expense_edit", args=[own.pk]))
    settings.DEBUG = True
    settings.REACT_EXPENSES_PILOT = False
    for path in routes:
        assert writer.get(path).templates[0].name == "expenses/expense_form.html"

    settings.REACT_EXPENSES_PILOT = True
    for path in routes:
        response = writer.get(
            path, {"month": "all", "search": "market", "next": "//example.com"}
        )
        assert response.templates[0].name == "react_host.html"
        assert (
            response.context["app"]["form"]["returnUrl"]
            == "/expenses/?month=all&search=market"
        )
        assert "no-store" in response.headers["Cache-Control"]
        assert writer.post(path).status_code == 405
    assert writer.get(reverse("expense_edit", args=[foreign.pk])).status_code == 404
