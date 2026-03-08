from django.contrib.auth.models import User
from django.test import TestCase

from .helpers import categorize_expense, categorize_from_sources
from .models import Category


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
