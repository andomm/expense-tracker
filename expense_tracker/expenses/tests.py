from django.test import TestCase
from django.contrib.auth.models import User

from .models import Category
from .views import match_expense_to_category


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

    def test_receiver_match_returns_receiver_source(self):
        """When receiver keyword matches, matched_from is 'receiver'."""
        category, keyword, source = match_expense_to_category("Lidl Finland", "", self.user)
        self.assertEqual(category, self.grocery_cat)
        self.assertEqual(keyword, "lidl")
        self.assertEqual(source, "receiver")

    def test_description_fallback_when_receiver_has_no_match(self):
        """When receiver text exists but has no keyword match, description is tried."""
        category, keyword, source = match_expense_to_category("Unknown Payee", "neste oil", self.user)
        self.assertEqual(category, self.fuel_cat)
        self.assertEqual(keyword, "neste")
        self.assertEqual(source, "description")

    def test_description_used_when_receiver_is_blank(self):
        """When receiver is blank, description is tried directly."""
        category, keyword, source = match_expense_to_category("", "prisma buy", self.user)
        self.assertEqual(category, self.grocery_cat)
        self.assertEqual(keyword, "prisma")
        self.assertEqual(source, "description")

    def test_no_match_returns_none_triple(self):
        """When neither receiver nor description matches, all three values are None."""
        category, keyword, source = match_expense_to_category("Unknown shop", "misc purchase", self.user)
        self.assertIsNone(category)
        self.assertIsNone(keyword)
        self.assertIsNone(source)

    def test_receiver_match_takes_priority_over_description(self):
        """Receiver match is used even when description also matches a different category."""
        category, keyword, source = match_expense_to_category("Lidl Finland", "neste oil", self.user)
        self.assertEqual(category, self.grocery_cat)
        self.assertEqual(source, "receiver")

    def test_empty_receiver_and_description_returns_none(self):
        """Both empty strings produce no match."""
        category, keyword, source = match_expense_to_category("", "", self.user)
        self.assertIsNone(category)
        self.assertIsNone(keyword)
        self.assertIsNone(source)
