import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.db.models.signals import pre_delete
from django.urls import reverse

from .models import Category, Expense

JSON = "application/json"
FILTERS = {
    "month": "2026-03",
    "search": "fixture",
    "category_filter": "all",
    "order_by": "-date",
}


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="bulk-owner")


@pytest.fixture
def other(db):
    return User.objects.create_user(username="bulk-other")


@pytest.fixture
def expense(owner):
    def make(**overrides):
        return Expense.objects.create(
            **{
                "user": owner,
                "date": "2026-03-09",
                "receiver": "Fixture store",
                "amount": "-12.00",
                **overrides,
            }
        )

    return make


def post(client, action, body, **headers):
    return client.post(
        reverse(f"api:expense-bulk-{action}"), body, content_type=JSON, **headers
    )


def test_filtered_deletion_covers_both_pages_and_only_matching_owned_rows(
    writer, owner, other, expense
):
    root = Category.objects.create(user=owner, name="Root")
    child = Category.objects.create(user=owner, name="Child", parent=root)
    keep = [
        expense(date="2026-02-09", category_obj=child),
        expense(receiver="Not a match", category_obj=child),
        expense(),
        expense(user=other),
        expense(amount="0.00", category_obj=child),
    ]
    for _ in range(51):
        expense(category_obj=child)
    filters = {**FILTERS, "category_filter": str(root.pk)}
    listing = reverse("api:expenses")
    assert (
        writer.get(listing, {**filters, "page": 2}).json()["pagination"]["count"] == 51
    )

    preview = post(writer, "confirm", {"filters": filters})
    assert preview.status_code == 200
    assert preview.json()["count"] == 51
    result = post(writer, "delete", {"token": preview.json()["token"]})
    assert result.json() == {"affected_count": 51}
    assert writer.get(listing, filters).json()["rows"] == []
    assert set(Expense.objects.values_list("pk", flat=True)) == {row.pk for row in keep}


def test_explicit_recategorization_preserves_amount_and_share_and_consumes_token(
    writer, owner, other, expense
):
    target = Category.objects.create(user=owner, name="Travel")
    chosen = expense(user_share="-5.00")
    same_day = expense()
    foreign = expense(user=other)
    ids = [chosen.pk]
    token = post(writer, "confirm", {"ids": ids}).json()["token"]
    body = {"ids": ids, "token": token, "category_id": target.pk}
    assert post(writer, "recategorize", body).json() == {"affected_count": 1}

    alternate = Category.objects.create(user=owner, name="Food")
    replay = post(writer, "recategorize", {**body, "category_id": alternate.pk})
    assert (replay.status_code, replay.json()["code"]) == (409, "stale_selection")
    chosen.refresh_from_db()
    assert (chosen.category_obj_id, chosen.category) == (target.pk, "Travel")
    assert str(chosen.amount) == "-12.00"
    assert str(chosen.user_share) == "-5.00"
    assert not Expense.objects.filter(
        pk__in=[same_day.pk, foreign.pk], category_obj=target
    ).exists()


@pytest.mark.parametrize("action", ["delete", "recategorize"])
def test_same_count_membership_change_is_stale(writer, owner, expense, action):
    target = Category.objects.create(user=owner, name="Destination")
    original = expense()
    unchanged = expense()
    token = post(writer, "confirm", {"filters": FILTERS}).json()["token"]
    Expense.objects.filter(pk=original.pk).update(receiver="Moved out")
    replacement = expense()
    payload = {
        "token": token,
        **({"category_id": target.pk} if action == "recategorize" else {}),
    }
    response = post(writer, action, payload)
    assert (response.status_code, response.json()["code"]) == (409, "stale_selection")
    assert set(Expense.objects.values_list("pk", "category_obj_id")) == {
        (row.pk, None) for row in [original, unchanged, replacement]
    }


@pytest.mark.parametrize("using_other_account", [True, False])
def test_token_is_bound_to_original_session(
    writer, owner, other, expense, using_other_account, csrf_client
):
    kept = expense()
    token = post(writer, "confirm", {"filters": FILTERS}).json()["token"]
    second = csrf_client(other if using_other_account else owner)
    response = post(second, "delete", {"token": token})
    assert (response.status_code, response.json()["code"]) == (409, "stale_selection")
    assert Expense.objects.filter(pk=kept.pk).exists()
    assert post(writer, "delete", {"token": token}).json() == {"affected_count": 1}


def test_explicit_confirmation_rejects_empty_selection(writer, expense):
    kept = expense()

    response = post(writer, "confirm", {"ids": []})

    assert response.status_code == 400
    assert Expense.objects.filter(pk=kept.pk).exists()


def test_explicit_scope_and_invalid_destination_do_not_partially_write(
    writer, other, expense
):
    foreign = expense(user=other)
    chosen = expense()
    no_scope = post(writer, "confirm", {"ids": [chosen.pk, foreign.pk]})
    assert (no_scope.status_code, no_scope.json()["code"]) == (404, "not_found")

    destination = Category.objects.create(user=other, name="Private destination")
    token = post(writer, "confirm", {"ids": [chosen.pk]}).json()["token"]
    invalid_target = post(
        writer,
        "recategorize",
        {
            "token": token,
            "ids": [chosen.pk],
            "category_id": destination.pk,
        },
    )
    assert (invalid_target.status_code, invalid_target.json()["code"]) == (
        422,
        "validation_failed",
    )
    assert set(Expense.objects.values_list("pk", "category_obj_id")) == {
        (chosen.pk, None),
        (foreign.pk, None),
    }
    changed_ids = post(
        writer, "delete", {"token": token, "ids": [chosen.pk, foreign.pk]}
    )
    assert changed_ids.status_code == 409
    assert Expense.objects.count() == 2


@pytest.mark.parametrize("action", ["confirm", "delete", "recategorize"])
def test_bulk_endpoints_enforce_csrf_and_require_session(
    writer, expense, action, csrf_client
):
    kept = expense()
    response = post(writer, action, {}, HTTP_X_CSRFTOKEN="")
    assert (response.status_code, response.json()["code"]) == (403, "csrf_failed")
    response = post(csrf_client(), action, {})
    assert (response.status_code, response.json()["code"]) == (401, "sign_in_required")
    assert Expense.objects.filter(pk=kept.pk).exists()


def test_failed_last_batch_rolls_back_first_batch_and_confirmation(writer, owner):
    rows = Expense.objects.bulk_create(
        [
            Expense(
                user=owner, date="2026-03-09", receiver="Fixture store", amount="-12.00"
            )
            for _ in range(501)
        ]
    )
    token = post(writer, "confirm", {"filters": FILTERS}).json()["token"]

    def fail_last_batch(sender, instance, **kwargs):
        if instance.pk == rows[-1].pk:
            raise IntegrityError("Fixture rejects the last deletion")

    pre_delete.connect(fail_last_batch, sender=Expense)
    try:
        with pytest.raises(IntegrityError, match="Fixture rejects"):
            post(writer, "delete", {"token": token})
    finally:
        pre_delete.disconnect(fail_last_batch, sender=Expense)

    assert Expense.objects.count() == 501
    assert post(writer, "delete", {"token": token}).json() == {"affected_count": 501}
