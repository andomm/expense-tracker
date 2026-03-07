from django.test import TestCase
from django.contrib.auth.models import User

from .models import Category
from .views import categorize_expense_by_description


class TwoStageMatchingTests(TestCase):
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

    def test_receiver_match(self):
        """Receiver text that contains a keyword matches correctly."""
        category, keyword = categorize_expense_by_description("Lidl Finland", self.user)
        self.assertEqual(category, self.grocery_cat)
        self.assertEqual(keyword, "lidl")

    def test_description_fallback_when_receiver_has_no_match(self):
        """When receiver text yields no match, description is tried separately."""
        # Receiver alone: no match
        category, keyword = categorize_expense_by_description("Unknown Payee", self.user)
        self.assertIsNone(category)

        # Description fallback: match
        category, keyword = categorize_expense_by_description("neste oil", self.user)
        self.assertEqual(category, self.fuel_cat)
        self.assertEqual(keyword, "neste")

    def test_description_used_when_receiver_is_blank(self):
        """Blank receiver skips to description matching."""
        category, keyword = categorize_expense_by_description("prisma buy", self.user)
        self.assertEqual(category, self.grocery_cat)
        self.assertEqual(keyword, "prisma")

    def test_no_match_returns_none_pair(self):
        """When text has no matching keyword, both values are None."""
        category, keyword = categorize_expense_by_description("misc purchase", self.user)
        self.assertIsNone(category)
        self.assertIsNone(keyword)

    def test_empty_text_returns_none(self):
        """Empty string produces no match."""
        category, keyword = categorize_expense_by_description("", self.user)
        self.assertIsNone(category)
        self.assertIsNone(keyword)
