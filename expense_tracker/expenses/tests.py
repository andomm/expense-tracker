from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .forms import CategoryForm
from .helpers import categorize_expense, categorize_from_sources
from .models import MAX_CATEGORY_DEPTH, Category, Expense


class CategorizeExpenseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass")
        self.grocery_cat = Category.objects.create(
            user=self.user,
            name="Groceries",
            keywords="lidl,prisma,k-market",
        )
        self.fuel_cat = Category.objects.create(
            user=self.user,
            name="Fuel",
            keywords="neste,abc fuel",
        )

    def test_matches_keyword_in_text(self):
        category, keyword = categorize_expense("Lidl Finland", self.user)

        self.assertEqual(category, self.grocery_cat)
        self.assertEqual(keyword, "lidl")

    def test_no_match_returns_none_pair(self):
        category, keyword = categorize_expense("misc purchase", self.user)

        self.assertIsNone(category)
        self.assertIsNone(keyword)

    def test_empty_text_returns_none_pair(self):
        category, keyword = categorize_expense("", self.user)

        self.assertIsNone(category)
        self.assertIsNone(keyword)

    def test_prefers_subcategory_over_parent(self):
        parent = Category.objects.create(
            user=self.user,
            name="Freetime",
            keywords="steam",
        )
        subcategory = Category.objects.create(
            user=self.user,
            name="Gaming",
            parent=parent,
            keywords="steam,psn",
        )

        category, keyword = categorize_expense("Steam Purchase", self.user)

        self.assertEqual(category, subcategory)
        self.assertEqual(keyword, "steam")

    def test_matches_parent_category_when_no_subcategory_matches(self):
        parent = Category.objects.create(
            user=self.user,
            name="Utilities",
            keywords="fortum",
        )
        Category.objects.create(
            user=self.user,
            name="Electricity",
            parent=parent,
            keywords="helen",
        )

        category, keyword = categorize_expense("Fortum invoice", self.user)

        self.assertEqual(category, parent)
        self.assertEqual(keyword, "fortum")

    def test_prefers_deepest_matching_category(self):
        """A category at depth 3 should win over depth 2 and depth 1."""
        lvl1 = Category.objects.create(user=self.user, name="Freetime", keywords="steam")
        lvl2 = Category.objects.create(user=self.user, name="Gaming", parent=lvl1, keywords="steam")
        lvl3 = Category.objects.create(user=self.user, name="PC Gaming", parent=lvl2, keywords="steam")

        category, keyword = categorize_expense("Steam Purchase", self.user)

        self.assertEqual(category, lvl3)
        self.assertEqual(keyword, "steam")


class CategorizeFromSourcesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass")
        self.grocery_cat = Category.objects.create(
            user=self.user,
            name="Groceries",
            keywords="lidl,prisma,k-market",
        )
        self.fuel_cat = Category.objects.create(
            user=self.user,
            name="Fuel",
            keywords="neste,abc fuel",
        )

    def test_matches_receiver_first(self):
        match = categorize_from_sources(
            ("receiver", "Lidl Finland"),
            ("description", "neste oil"),
            user=self.user,
        )

        self.assertEqual(match.category, self.grocery_cat)
        self.assertEqual(match.keyword, "lidl")
        self.assertEqual(match.source, "receiver")

    def test_falls_back_to_description(self):
        match = categorize_from_sources(
            ("receiver", "Unknown Payee"),
            ("description", "neste oil"),
            user=self.user,
        )

        self.assertEqual(match.category, self.fuel_cat)
        self.assertEqual(match.keyword, "neste")
        self.assertEqual(match.source, "description")

    def test_returns_none_when_no_sources_match(self):
        match = categorize_from_sources(
            ("receiver", "Unknown Payee"),
            ("description", "misc purchase"),
            user=self.user,
        )

        self.assertIsNone(match.category)
        self.assertIsNone(match.keyword)
        self.assertIsNone(match.source)


class CategoryHierarchyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tree-user", password="pass")

    def test_get_all_keywords_includes_all_descendant_keywords(self):
        parent = Category.objects.create(
            user=self.user,
            name="Freetime",
            keywords="cinema,steam",
        )
        child = Category.objects.create(
            user=self.user,
            name="Gaming",
            parent=parent,
            keywords="steam,psn",
        )
        Category.objects.create(
            user=self.user,
            name="PC Gaming",
            parent=child,
            keywords="gog,epic",
        )

        # Root should aggregate all unique keywords from the full subtree
        self.assertEqual(parent.get_all_keywords(), "cinema,steam,psn,gog,epic")

    def test_allows_up_to_max_depth(self):
        """Should be possible to create a chain of MAX_CATEGORY_DEPTH levels."""
        cat = Category.objects.create(user=self.user, name="Level1", keywords="")
        for i in range(2, MAX_CATEGORY_DEPTH + 1):
            cat = Category.objects.create(user=self.user, name=f"Level{i}", parent=cat, keywords="")
        # No error means it passed; verify depth
        self.assertEqual(cat.get_depth(), MAX_CATEGORY_DEPTH)

    def test_prevents_exceeding_max_depth(self):
        cat = Category.objects.create(user=self.user, name="Level1", keywords="")
        for i in range(2, MAX_CATEGORY_DEPTH + 1):
            cat = Category.objects.create(user=self.user, name=f"Level{i}", parent=cat, keywords="")

        # One more level should fail
        too_deep = Category(user=self.user, name="TooDeep", parent=cat, keywords="")
        with self.assertRaises(ValidationError):
            too_deep.full_clean()

    def test_prevents_third_level_categories(self):
        """Backward-compat test: depth 3 still allowed, depth 6 is not."""
        parent = Category.objects.create(
            user=self.user,
            name="Freetime",
            keywords="cinema",
        )
        child = Category.objects.create(
            user=self.user,
            name="Gaming",
            parent=parent,
            keywords="steam",
        )
        grandchild = Category(
            user=self.user,
            name="PC Gaming",
            parent=child,
            keywords="gog",
        )
        # depth 3 should be fine (MAX_CATEGORY_DEPTH = 5)
        grandchild.full_clean()  # should not raise


class DefaultCategoryOwnershipTests(TestCase):
    def setUp(self):
        self.template_parent = Category.objects.create(
            user=None,
            name="Default Parent",
            category_type=Category.CATEGORY_TYPE_EXPENSE,
            keywords="rent",
            is_system=True,
        )
        self.template_child = Category.objects.create(
            user=None,
            name="Default Child",
            parent=self.template_parent,
            category_type=Category.CATEGORY_TYPE_EXPENSE,
            keywords="power",
            is_system=True,
        )

    def test_new_user_gets_user_owned_copies_of_system_templates(self):
        user = User.objects.create_user(username="seed-user", password="pass")

        user_parent = Category.objects.get(user=user, name="Default Parent")
        user_child = Category.objects.get(user=user, name="Default Child")

        self.assertFalse(user_parent.is_system)
        self.assertFalse(user_child.is_system)
        self.assertEqual(user_child.parent, user_parent)

    def test_categorization_uses_user_owned_copy_not_shared_template(self):
        user = User.objects.create_user(username="seed-match-user", password="pass")

        category, keyword = categorize_expense("Monthly power bill", user)

        self.assertIsNotNone(category)
        self.assertEqual(keyword, "power")
        self.assertEqual(category.user, user)
        self.assertFalse(category.is_system)


class ExpenseListSummaryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="summaryuser", password="pass")
        self.client.force_login(self.user)

        self.expense_category = Category.objects.create(
            user=self.user,
            name="Groceries",
            category_type=Category.CATEGORY_TYPE_EXPENSE,
        )
        self.saving_category, _ = Category.objects.get_or_create(
            user=self.user,
            name="Savings",
            defaults={"category_type": Category.CATEGORY_TYPE_SAVING},
        )
        self.income_category = Category.objects.create(
            user=self.user,
            name="Salary",
            category_type=Category.CATEGORY_TYPE_INCOME,
        )
        self.transfer_category, _ = Category.objects.get_or_create(
            user=self.user,
            name="Transfers",
            defaults={"category_type": Category.CATEGORY_TYPE_TRANSFER},
        )

    def test_summary_includes_absolute_savings_total(self):
        Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 9),
            category=self.expense_category.name,
            category_obj=self.expense_category,
            amount="-20.00",
            user_share="-20.00",
            receiver="Grocery store",
        )
        Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 9),
            category=self.saving_category.name,
            category_obj=self.saving_category,
            amount="-50.00",
            user_share="-50.00",
            receiver="Savings account",
        )
        Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 9),
            category=self.income_category.name,
            category_obj=self.income_category,
            amount="100.00",
            user_share="100.00",
            receiver="Employer",
        )
        Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 9),
            category=self.transfer_category.name,
            category_obj=self.transfer_category,
            amount="-30.00",
            user_share="-30.00",
            receiver="Own account",
        )

        response = self.client.get(reverse("api:expenses"), {"month": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["total_spent"], "-20.00")
        self.assertEqual(response.json()["summary"]["income"], "100.00")
        self.assertEqual(response.json()["summary"]["savings_total"], "50.00")
        self.assertEqual(response.json()["summary"]["balance"], "80.00")

    def test_top_expenses_link_to_edit_page(self):
        expense = Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 9),
            category=self.expense_category.name,
            category_obj=self.expense_category,
            amount="-20.00",
            user_share="-20.00",
            receiver="Grocery store",
        )

        response = self.client.get(reverse("api:expenses"), {"month": "all"})

        self.assertEqual(response.status_code, 200)
        [row] = response.json()["top_expenses"]
        self.assertEqual(row["edit_url"], reverse("expense_edit", args=[expense.pk]))


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("split_values", "expected"),
    [
        ([("Sports", "30.00")], {"General": "-70.00", "Sports": "-30.00"}),
        ([("Sports", "60.00"), ("Utilities", "40.00")], {"Sports": "-60.00", "Utilities": "-40.00"}),
        ([("Sports", "30.00"), ("Utilities", "20.00")], {"General": "-50.00", "Sports": "-30.00", "Utilities": "-20.00"}),
        ([("Savings", "20.00")], {"General": "-80.00", "Savings": "-20.00"}),
    ],
    ids=["partial", "full", "independent-rows", "savings"],
)
def test_create_expense_splits_are_independent_rows_with_correct_summary(client, split_values, expected):
    user = User.objects.create_user(username="split-user")
    client.force_login(user)
    categories = {
        name: Category.objects.get_or_create(user=user, name=name)[0]
        for name in ["General", "Sports", "Utilities", "Savings"]
    }
    url = reverse("api:expenses")
    response = client.post(
        url,
        {
            "date": "2026-03-09",
            "description": "Sports store",
            "amount": "-100.00",
            "category_id": categories["General"].pk,
            "receiver": "Superstore",
            "splits": [
                {"category_id": categories[name].pk, "amount": amount}
                for name, amount in split_values
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    listing = client.get(url, {"month": "all"}).json()
    rows = listing["rows"]
    assert len(rows) == len({row["id"] for row in rows}) == len(expected)
    assert {row["category"]["name"]: row["amount"] for row in rows} == expected
    assert {(row["date"], row["receiver"]) for row in rows} == {("2026-03-09", "Superstore")}
    if "Savings" in expected:
        assert listing["summary"]["total_spent"] == "-80.00"
        assert listing["summary"]["savings_total"] == "20.00"


class CategoryManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="category-owner", password="pass")
        self.client.force_login(self.user)

    def test_user_can_edit_seeded_default_category(self):
        category = Category.objects.get(user=self.user, name="Savings")

        response = self.client.put(
            reverse("api:category-detail", args=[category.pk]),
            {
                "name": "Emergency Fund",
                "parent_id": None,
                "category_type": Category.CATEGORY_TYPE_SAVING,
                "keywords": "save,emergency",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        category.refresh_from_db()
        self.assertEqual(category.name, "Emergency Fund")
        self.assertEqual(category.keywords, "save,emergency")

    def test_user_can_delete_seeded_default_category(self):
        category = Category.objects.get(user=self.user, name="Transfers")

        response = self.client.delete(reverse("api:category-detail", args=[category.pk]))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Category.objects.filter(pk=category.pk).exists())
        self.assertTrue(
            Category.objects.filter(
                user__isnull=True,
                is_system=True,
                name="Transfers",
            ).exists()
        )

@pytest.fixture
def category_form_account(db):
    owner = User.objects.create_user(username="keyword-owner")
    Category.objects.filter(user=owner).delete()
    food = Category.objects.create(user=owner, name="Food", keywords="lidl,prisma")
    Category.objects.create(user=owner, name="Hypermarkets", parent=food, keywords="citymarket")
    Category.objects.create(user=owner, name="Fuel", keywords="neste,abc")
    other = User.objects.create_user(username="other-keyword-owner")
    Category.objects.create(user=other, name="Private", keywords="uber")
    return owner, food


@pytest.mark.parametrize(
    ("instance_name", "submitted", "conflicts"),
    [
        ("", "lidl,k-market", ["'lidl' is already used by category 'Food'"]),
        ("", "citymarket", ["'citymarket' is already used by category 'Hypermarkets'"]),
        ("", "LIDL", ["'lidl' is already used by category 'Food'"]),
        ("", "lidl,neste", ["'lidl' is already used by category 'Food'", "'neste' is already used by category 'Fuel'"]),
        ("Travel", "uber,taxi,lidl", ["'lidl' is already used by category 'Food'"]),
        ("Food", "lidl,prisma,k-market", []),
        ("", "train,taxi", []),
        ("", "uber", []),
    ],
    ids=[
        "different-category", "descendant", "case-insensitive", "multiple-conflicts",
        "edit-conflict", "keep-own-keywords", "unique", "other-user",
    ],
)
def test_keyword_validation_is_scoped_to_other_categories_of_current_user(
    category_form_account, instance_name, submitted, conflicts
):
    owner, food = category_form_account
    if instance_name == "Food":
        instance = food
    elif instance_name == "Travel":
        instance = Category.objects.create(user=owner, name=instance_name, keywords="uber,taxi")
    else:
        instance = Category(user=owner)
    form = CategoryForm(
        {"name": instance_name or "Transit", "category_type": "expense", "keywords": submitted},
        instance=instance,
        user=owner,
    )

    assert form.is_valid() is (not conflicts)
    if conflicts:
        assert set(form.errors) == {"keywords"}
        for message in conflicts:
            assert message in form.errors["keywords"][0]
    else:
        assert form.save().keywords == submitted


class ExpenseAnalyticsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="analyticsuser", password="pass")
        self.client.force_login(self.user)

        self.march_category = Category.objects.create(
            user=self.user,
            name="March Pie Category",
            category_type=Category.CATEGORY_TYPE_EXPENSE,
        )
        self.february_category = Category.objects.create(
            user=self.user,
            name="February Pie Category",
            category_type=Category.CATEGORY_TYPE_EXPENSE,
        )
    def test_selected_month_only_filters_pie_chart(self):
        Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 9),
            category=self.march_category.name,
            category_obj=self.march_category,
            amount="-20.00",
            user_share="-20.00",
            receiver="March store",
        )
        Expense.objects.create(
            user=self.user,
            date=date(2026, 2, 9),
            category=self.february_category.name,
            category_obj=self.february_category,
            amount="-30.00",
            user_share="-30.00",
            receiver="February store",
        )

        response = self.client.get(reverse("api:analytics"), {"month": "2026-03"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        category = data["category"]
        self.assertEqual(
            (category["label"], category["previous"], category["next"]),
            ("March 2026", "2026-02", "2026-04"),
        )
        self.assertEqual([row["name"] for row in category["rows"]], ["March Pie Category"])
        self.assertEqual(data["yearly"], [{"year": 2026, "total_spent": "50.00"}])

    def test_split_expenses_contribute_to_monthly_analytics(self):
        general = Category.objects.create(
            user=self.user,
            name="General",
            category_type=Category.CATEGORY_TYPE_EXPENSE,
        )
        sports = Category.objects.create(
            user=self.user,
            name="Sports",
            category_type=Category.CATEGORY_TYPE_EXPENSE,
        )
        Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 12),
            category=general.name,
            category_obj=general,
            amount="-70.00",
            receiver="Sports shop",
        )
        Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 12),
            category=sports.name,
            category_obj=sports,
            amount="-30.00",
            receiver="Sports shop",
        )

        response = self.client.get(reverse("api:analytics"), {"month": "2026-03"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["monthly"], [{"month": "2026-03", "total_spent": "100.00"}])
        self.assertEqual(data["yearly"], [{"year": 2026, "total_spent": "100.00"}])
        self.assertEqual(
            [(row["name"], row["amount"]) for row in data["category"]["rows"]],
            [("General", "70.00"), ("Sports", "30.00")],
        )
