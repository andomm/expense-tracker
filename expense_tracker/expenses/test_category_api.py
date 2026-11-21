from datetime import date

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from .forms import CategoryForm
from .models import Category, Expense


@pytest.fixture
def accounts(db):
    owners = [User.objects.create_user(name) for name in ("category-owner", "other-owner")]
    Category.objects.filter(user__in=owners).delete()
    return owners


@pytest.fixture
def account_client(accounts):
    client = Client(enforce_csrf_checks=True)
    client.force_login(accounts[0])
    return client


@pytest.fixture
def make_category(accounts):
    def make(name, *, owner=accounts[0], **fields):
        return Category.objects.create(user=owner, name=name, **fields)

    return make


def test_tree_matches_legacy_root_totals_without_exposing_other_categories(
    account_client, accounts, make_category, settings
):
    root = make_category("Travel", keywords="Rail, rail")
    child = make_category("Local", parent=root, keywords="bus, RAIL")
    leaf = make_category("Trams", parent=child, keywords="tram, bus")
    make_category("Other user's branch", owner=accounts[1], parent=root, keywords="secret")
    make_category("Other user's root", owner=accounts[1])
    make_category("Income", category_type="income")

    response = account_client.get(reverse("api:categories"))
    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    assert [
        (entry["name"], entry["parent_id"], entry["category_type"], entry["keyword_count"])
        for entry in response.json()["categories"]
    ] == [
        ("Income", None, "income", 0),
        ("Travel", None, "expense", 3),
        ("Local", root.pk, "expense", 2),
        ("Trams", child.pk, "expense", 2),
    ]
    settings.LEGACY_PAGES = True
    legacy = account_client.get(reverse("category_list")).context["category_groups"]
    assert legacy[1]["parent_keyword_count"] == 3
    assert legacy[1]["parent_keywords_full"] == "rail, bus, tram"
    assert [entry["category"].pk for entry in legacy[1]["children"]] == [child.pk, leaf.pk]


def test_form_parent_choices_leave_room_for_the_whole_subtree(accounts, make_category):
    root = make_category("Travel")
    moving = make_category("Trains", parent=root)
    leaf = make_category("Night trains", parent=moving)
    depth_three = make_category("Level three", parent=make_category("Level two", parent=root))
    depth_four = make_category("Level four", parent=depth_three)
    deepest = make_category("Level five", parent=depth_four)
    foreign = make_category("Private parent", owner=accounts[1])
    form = CategoryForm(user=accounts[0], instance=moving)
    offered = {value for value, _ in form.fields["parent"].choices}
    assert str(depth_three.pk) in offered
    assert offered.isdisjoint(str(cat.pk) for cat in (moving, leaf, depth_four, deepest, foreign))

    data = {"name": moving.name, "category_type": "expense"}
    for parent in (moving, leaf, depth_four, foreign):
        invalid = CategoryForm({**data, "parent": parent.pk}, user=accounts[0], instance=moving)
        assert not invalid.is_valid()
        assert set(invalid.errors) == {"parent"}
    valid = CategoryForm({**data, "parent": depth_three.pk}, user=accounts[0], instance=moving)
    assert valid.is_valid(), valid.errors
    valid.save()
    leaf.refresh_from_db()
    assert leaf.get_depth() == 5


def test_form_rejects_type_changes_that_would_leave_children_mismatched(accounts, make_category):
    root = make_category("Travel")
    child = make_category("Trains", parent=root)
    for instance in (root, child):
        form = CategoryForm(
            {"name": instance.name, "parent": instance.parent_id, "category_type": "saving"},
            instance=instance, user=accounts[0],
        )
        assert not form.is_valid()
        assert set(form.errors) == {"category_type"}


@pytest.fixture
def write(account_client):
    token = account_client.get(reverse("api:session")).json()["csrf_token"]

    def send(method, url, data=None):
        options = {"headers": {"X-CSRFToken": token}}
        if data is not None:
            options.update(data=data, content_type="application/json")
        return getattr(account_client, method)(url, **options)

    return send


def category_data(name, *, parent_id=None, category_type="expense", keywords=""):
    return {"name": name, "parent_id": parent_id, "category_type": category_type, "keywords": keywords}


def test_create_then_edit_keywords_without_recategorizing_expenses(
    account_client, write, accounts, make_category
):
    root = make_category("Groceries")
    expense = Expense.objects.create(
        user=accounts[0], date=date(2026, 10, 1), amount="-12.35", receiver="APPLE", category_obj=root
    )
    unmatched = Expense.objects.create(
        user=accounts[0], date=date(2026, 10, 1), amount="-5.50", receiver="pear"
    )
    foreign = make_category("Private", owner=accounts[1], keywords="pear")
    options = account_client.get(reverse("api:category-form-options")).json()
    assert options["parent_choices"] == [{"id": root.pk, "label": "Groceries"}]
    assert [option["id"] for option in options["category_types"]] == [
        "expense", "saving", "transfer", "income"
    ]

    response = write("post", reverse("api:categories"), category_data("Fruit", parent_id=root.pk))
    assert response.status_code == 201
    new_id = response.json()["id"]
    detail = reverse("api:category-detail", args=[new_id])
    response = write("put", detail, category_data("Fruit", parent_id=root.pk, keywords="APPLE, pear"))
    assert response.status_code == 200
    result = account_client.get(detail).json()
    assert (result["id"], result["name"], result["parent_id"], result["keywords"]) == (
        new_id, "Fruit", root.pk, "APPLE, pear"
    )
    assert result["parent_choices"] == options["parent_choices"]
    expense.refresh_from_db()
    unmatched.refresh_from_db()
    assert (expense.category_obj_id, unmatched.category_obj_id) == (root.pk, None)
    assert Category.objects.filter(user=accounts[1]).get().pk == foreign.pk


@pytest.mark.parametrize("failure", ["foreign_parent", "missing_parent", "keywords", "name"])
def test_rejected_edit_reports_the_relevant_field_without_changing_category(
    write, accounts, make_category, failure
):
    root = make_category("Travel", keywords="Train")
    moving = make_category("Cafe", keywords="coffee")
    foreign = make_category("Private", owner=accounts[1])
    cases = {
        "foreign_parent": ("parent_id", foreign.pk),
        "missing_parent": ("parent_id", foreign.pk + 1),
        "keywords": ("keywords", "  TRAIN  "),
        "name": ("name", root.name),
    }
    field, value = cases[failure]
    data = category_data("Edited Cafe", parent_id=root.pk, keywords="Tea")
    data[field] = value
    response = write("put", reverse("api:category-detail", args=[moving.pk]), data)
    assert response.status_code == 422
    assert set(response.json()["fields"]) == {field}
    if field == "parent_id":
        assert response.json()["fields"][field] == [
            "Select a valid choice. That choice is not one of the available choices."
        ]
    moving.refresh_from_db()
    assert (moving.name, moving.keywords, moving.parent_id) == ("Cafe", "coffee", None)


def test_deleting_a_category_uncategorizes_only_its_expenses_and_promotes_direct_children(
    account_client, write, accounts, make_category
):
    root = make_category("Travel")
    deleted = make_category("Rail", parent=root)
    child = make_category("Night trains", parent=deleted)
    grandchild = make_category("Sleepers", parent=child)
    private = make_category("Private rail", owner=accounts[1])
    expenses = [
        Expense.objects.create(user=owner, date=date(2026, 10, 1), amount=amount, category_obj=category)
        for owner, amount, category in (
            (accounts[0], "-12.35", deleted), (accounts[0], "-5.50", child), (accounts[1], "-8.01", private)
        )
    ]
    url = reverse("api:category-detail", args=[deleted.pk])
    assert write("delete", url).status_code == 204
    assert account_client.get(url).status_code == 404
    for record in [*expenses, child, grandchild]:
        record.refresh_from_db()
    assert (child.parent_id, grandchild.parent_id) == (None, child.pk)
    assert [expense.category_obj_id for expense in expenses] == [None, child.pk, private.pk]
    assert [str(expense.amount) for expense in expenses] == ["-12.35", "-5.50", "-8.01"]


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_foreign_category_id_is_indistinguishable_from_missing(
    account_client, write, accounts, make_category, method
):
    private = make_category("Private", owner=accounts[1], keywords="secret")
    data = category_data("Edited") if method == "put" else None
    for pk in (private.pk, private.pk + 1):
        url = reverse("api:category-detail", args=[pk])
        response = account_client.get(url) if method == "get" else write(method, url, data)
        assert response.status_code == 404
        assert response.json() == {"code": "not_found", "message": "This category was not found."}
    private.refresh_from_db()
    assert private.name == "Private"


def test_category_writes_require_csrf_and_reject_an_expired_session(
    account_client, write, accounts
):
    url = reverse("api:categories")
    data = category_data("Travel")
    response = account_client.post(url, data, content_type="application/json")
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"

    account_client.session.delete()
    for response in (account_client.get(url), write("post", url, data)):
        assert response.status_code == 401
        assert response.json()["code"] == "sign_in_required"
    assert not Category.objects.filter(user=accounts[0]).exists()


@pytest.mark.parametrize(
    ("local", "debug", "legacy", "candidate", "react"),
    [(True, True, False, True, True), (True, True, False, False, False),
     (True, True, True, True, False), (False, True, False, True, False),
     (True, False, False, True, False)],
    ids=["candidate", "default", "fallback", "plain-django", "debug-disabled"],
)
def test_only_explicit_category_crud_pages_migrate(
    account_client, accounts, make_category, settings, local, debug, legacy, candidate, react
):
    settings.LOCAL_REACT_DEV = local
    settings.DEBUG = debug
    settings.LEGACY_PAGES = legacy
    settings.CATEGORY_REACT_CANDIDATE = candidate
    owned = make_category("Travel")
    foreign = make_category("Private", owner=accounts[1])
    pages = [
        ("category_list", [], "category_list", "categories"),
        ("category_add", [], "category_form", "category-add"),
        ("category_edit", [owned.pk], "category_form", "category-edit"),
        ("category_delete", [owned.pk], "category_confirm_delete", "category-delete"),
    ]
    for path_name, args, template, screen in pages:
        response = account_client.get(reverse(path_name, args=args))
        assert response.templates[0].name == ("react_host.html" if react else f"expenses/{template}.html")
        if react:
            assert response.context["app"]["screen"] == screen
    for path_name in ("category_edit", "category_delete"):
        assert account_client.get(reverse(path_name, args=[foreign.pk])).status_code == 404
    assert account_client.get(reverse("sync_categories")).url == reverse("category_list")
    assert account_client.get(reverse("sync_summary")).templates[0].name == "expenses/sync_summary.html"
