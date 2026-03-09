from datetime import date

from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .helpers import categorize_expense, categorize_from_sources
from .models import Category, Expense


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
        from expenses.models import MAX_CATEGORY_DEPTH
        cat = Category.objects.create(user=self.user, name="Level1", keywords="")
        for i in range(2, MAX_CATEGORY_DEPTH + 1):
            cat = Category.objects.create(user=self.user, name=f"Level{i}", parent=cat, keywords="")
        # No error means it passed; verify depth
        self.assertEqual(cat.get_depth(), MAX_CATEGORY_DEPTH)

    def test_prevents_exceeding_max_depth(self):
        from expenses.models import MAX_CATEGORY_DEPTH
        cat = Category.objects.create(user=self.user, name="Level1", keywords="")
        for i in range(2, MAX_CATEGORY_DEPTH + 1):
            cat = Category.objects.create(user=self.user, name=f"Level{i}", parent=cat, keywords="")

        # One more level should fail
        too_deep = Category(user=self.user, name="TooDeep", parent=cat, keywords="")
        with self.assertRaises(ValidationError):
            too_deep.full_clean()

    def test_prevents_third_level_categories(self):
        """Backward-compat test: depth 3 still allowed, depth 6 is not."""
        from expenses.models import MAX_CATEGORY_DEPTH
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


class ExpenseListCategoryFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="filter-user", password="pass")
        self.client.force_login(self.user)
        self.parent = Category.objects.create(
            user=self.user,
            name="Freetime",
            keywords="cinema",
        )
        self.child = Category.objects.create(
            user=self.user,
            name="Gaming",
            parent=self.parent,
            keywords="steam",
        )
        self.other = Category.objects.create(
            user=self.user,
            name="Utilities",
            keywords="power",
        )

    def test_parent_filter_includes_subcategory_expenses(self):
        parent_expense = Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 9),
            category=self.parent.name,
            category_obj=self.parent,
            amount="-10.00",
            receiver="Cinema",
        )
        child_expense = Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 9),
            category=self.child.name,
            category_obj=self.child,
            amount="-20.00",
            receiver="Steam",
        )
        Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 9),
            category=self.other.name,
            category_obj=self.other,
            amount="-30.00",
            receiver="Power company",
        )

        response = self.client.get(
            reverse("expense_list"),
            {"month": "all", "category_filter": str(self.parent.pk)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(
            response.context["expenses"].order_by("pk"),
            [parent_expense.pk, child_expense.pk],
            transform=lambda expense: expense.pk,
        )
