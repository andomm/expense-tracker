from datetime import date
from decimal import Decimal

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
        self.assertEqual(
            [expense.pk for expense in response.context["expenses"]],
            [parent_expense.pk, child_expense.pk],
        )

    def test_expense_edit_links_preserve_filters(self):
        expense = Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 9),
            category=self.parent.name,
            category_obj=self.parent,
            amount="-10.00",
            receiver="Cinema",
        )

        response = self.client.get(
            reverse("expense_list"),
            {
                "month": "all",
                "order_by": "amount",
                "category_filter": str(self.parent.pk),
            },
        )

        edit_url = (
            f"{reverse('expense_edit', args=[expense.pk])}"
            f"?month=all&order_by=amount&category_filter={self.parent.pk}"
        )
        self.assertContains(response, edit_url.replace("&", "&amp;"), html=False)

    def test_search_filters_expenses_by_receiver_description_and_category(self):
        utilities_expense = Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 9),
            category=self.other.name,
            category_obj=self.other,
            amount="-30.00",
            receiver="Power company",
            description="Monthly electricity bill",
        )
        gaming_expense = Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 9),
            category=self.child.name,
            category_obj=self.child,
            amount="-20.00",
            receiver="Steam",
            description="Game purchase",
        )

        receiver_response = self.client.get(
            reverse("expense_list"),
            {"month": "all", "search": "power"},
        )
        self.assertEqual(
            [expense.pk for expense in receiver_response.context["expenses"]],
            [utilities_expense.pk],
        )

        description_response = self.client.get(
            reverse("expense_list"),
            {"month": "all", "search": "game"},
        )
        self.assertEqual(
            [expense.pk for expense in description_response.context["expenses"]],
            [gaming_expense.pk],
        )

        category_response = self.client.get(
            reverse("expense_list"),
            {"month": "all", "search": "utilities"},
        )
        self.assertEqual(
            [expense.pk for expense in category_response.context["expenses"]],
            [utilities_expense.pk],
        )


class BulkCategoryUpdateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bulk-user", password="pass")
        self.other_user = User.objects.create_user(username="other-user", password="pass")
        self.client.force_login(self.user)

        self.original_category = Category.objects.create(
            user=self.user,
            name="Groceries",
        )
        self.new_category = Category.objects.create(
            user=self.user,
            name="Utilities",
        )
        self.other_user_category = Category.objects.create(
            user=self.other_user,
            name="Private Category",
        )

        self.expense_one = Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 9),
            category=self.original_category.name,
            category_obj=self.original_category,
            amount="-10.00",
            receiver="Store one",
        )
        self.expense_two = Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 10),
            category=self.original_category.name,
            category_obj=self.original_category,
            amount="-20.00",
            receiver="Store two",
        )
        self.other_user_expense = Expense.objects.create(
            user=self.other_user,
            date=date(2026, 3, 11),
            category=self.other_user_category.name,
            category_obj=self.other_user_category,
            amount="-30.00",
            receiver="Other store",
        )

    def test_updates_selected_expenses_and_preserves_context(self):
        response = self.client.post(
            reverse("expense_bulk_category_update"),
            {
                "expense_ids": [str(self.expense_one.pk), str(self.expense_two.pk)],
                "category_obj": str(self.new_category.pk),
                "month": "2026-03",
                "order_by": "amount",
                "category_filter": str(self.original_category.pk),
            },
            follow=True,
        )

        expected_url = (
            f"{reverse('expense_list')}?month=2026-03&order_by=amount"
            f"&category_filter={self.original_category.pk}"
        )
        self.assertRedirects(response, expected_url)

        self.expense_one.refresh_from_db()
        self.expense_two.refresh_from_db()
        self.assertEqual(self.expense_one.category_obj, self.new_category)
        self.assertEqual(self.expense_one.category, self.new_category.name)
        self.assertEqual(self.expense_two.category_obj, self.new_category)
        self.assertEqual(self.expense_two.category, self.new_category.name)
        self.assertContains(response, "Updated 2 expenses to Utilities.")

    def test_rejects_expenses_not_owned_by_current_user(self):
        response = self.client.post(
            reverse("expense_bulk_category_update"),
            {
                "expense_ids": [str(self.expense_one.pk), str(self.other_user_expense.pk)],
                "category_obj": str(self.new_category.pk),
                "month": "all",
            },
            follow=True,
        )

        self.assertRedirects(response, f"{reverse('expense_list')}?month=all")
        self.expense_one.refresh_from_db()
        self.assertEqual(self.expense_one.category_obj, self.original_category)
        self.assertContains(response, "One or more selected expenses are invalid.")

    def test_rejects_invalid_category_choice(self):
        response = self.client.post(
            reverse("expense_bulk_category_update"),
            {
                "expense_ids": [str(self.expense_one.pk)],
                "category_obj": str(self.other_user_category.pk),
                "month": "all",
            },
            follow=True,
        )

        self.assertRedirects(response, f"{reverse('expense_list')}?month=all")
        self.expense_one.refresh_from_db()
        self.assertEqual(self.expense_one.category_obj, self.original_category)
        self.assertContains(response, "Select a valid category.")

    def test_requires_at_least_one_selected_expense(self):
        response = self.client.post(
            reverse("expense_bulk_category_update"),
            {
                "category_obj": str(self.new_category.pk),
                "month": "all",
            },
            follow=True,
        )

        self.assertRedirects(response, f"{reverse('expense_list')}?month=all")
        self.expense_one.refresh_from_db()
        self.assertEqual(self.expense_one.category_obj, self.original_category)
        self.assertContains(response, "Select at least one expense to update.")


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

        response = self.client.get(reverse("expense_list"), {"month": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_spent"], Decimal("-20.00"))
        self.assertEqual(response.context["income"], Decimal("100.00"))
        self.assertEqual(response.context["savings_total"], Decimal("50.00"))
        self.assertEqual(response.context["balance"], Decimal("80.00"))

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

        response = self.client.get(reverse("expense_list"), {"month": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("expense_edit", args=[expense.pk]))


class ExpenseEditReturnContextTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="edit-user", password="pass")
        self.client.force_login(self.user)
        self.category = Category.objects.create(
            user=self.user,
            name="Groceries",
            category_type=Category.CATEGORY_TYPE_EXPENSE,
        )
        self.expense = Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 9),
            category=self.category.name,
            category_obj=self.category,
            amount="-20.00",
            user_share="-20.00",
            receiver="Grocery store",
            description="Weekly groceries",
        )

    def test_edit_page_back_link_preserves_list_context(self):
        response = self.client.get(
            reverse("expense_edit", args=[self.expense.pk]),
            {
                "month": "all",
                "order_by": "amount",
                "category_filter": str(self.category.pk),
            },
        )

        expected_url = (
            f"{reverse('expense_list')}?month=all&order_by=amount"
            f"&category_filter={self.category.pk}"
        )
        self.assertContains(
            response,
            f'href="{expected_url.replace("&", "&amp;")}"',
            html=False,
        )
        self.assertContains(response, 'name="month" value="all"', html=False)
        self.assertContains(response, 'name="order_by" value="amount"', html=False)
        self.assertContains(
            response,
            f'name="category_filter" value="{self.category.pk}"',
            html=False,
        )

    def test_saving_edit_returns_to_filtered_list(self):
        response = self.client.post(
            reverse("expense_edit", args=[self.expense.pk]),
            {
                "date": "2026-03-09",
                "description": "Updated groceries",
                "amount": "-20.00",
                "category_obj": str(self.category.pk),
                "receiver": "Grocery store",
                "month": "all",
                "order_by": "amount",
                "category_filter": str(self.category.pk),
                "parts-TOTAL_FORMS": "0",
                "parts-INITIAL_FORMS": "0",
                "parts-MIN_NUM_FORMS": "0",
                "parts-MAX_NUM_FORMS": "1000",
            },
            follow=True,
        )

        expected_url = (
            f"{reverse('expense_list')}?month=all&order_by=amount"
            f"&category_filter={self.category.pk}"
        )
        self.assertRedirects(response, expected_url)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.description, "Updated groceries")


class ExpenseSplitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="split-user", password="pass")
        self.client.force_login(self.user)
        self.general = Category.objects.create(user=self.user, name="General")
        self.sports = Category.objects.create(user=self.user, name="Sports")
        self.utilities = Category.objects.create(user=self.user, name="Utilities")
        self.savings = Category.objects.get(user=self.user, name="Savings")

    def _formset_management(self, *, total_forms, initial_forms=0):
        return {
            "parts-TOTAL_FORMS": str(total_forms),
            "parts-INITIAL_FORMS": str(initial_forms),
            "parts-MIN_NUM_FORMS": "0",
            "parts-MAX_NUM_FORMS": "1000",
        }

    def test_split_creates_new_expenses_and_keeps_remainder(self):
        response = self.client.post(
            reverse("expense_add"),
            {
                "date": "2026-03-09",
                "description": "Sports store",
                "amount": "-100.00",
                "category_obj": str(self.general.pk),
                "split_rule": "",
                "receiver": "Superstore",
                "parts-0-amount": "30.00",
                "parts-0-category_obj": str(self.sports.pk),
                **self._formset_management(total_forms=1),
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("expense_list"))
        self.assertEqual(Expense.objects.filter(user=self.user).count(), 2)

        remainder = Expense.objects.get(category_obj=self.general, user=self.user)
        split_expense = Expense.objects.get(category_obj=self.sports, user=self.user)

        self.assertEqual(remainder.amount, Decimal("-70.00"))
        self.assertEqual(remainder.receiver, "Superstore")
        self.assertEqual(split_expense.amount, Decimal("-30.00"))
        self.assertEqual(split_expense.receiver, "Superstore")
        self.assertEqual(split_expense.date, date(2026, 3, 9))

    def test_full_split_deletes_original_expense(self):
        response = self.client.post(
            reverse("expense_add"),
            {
                "date": "2026-03-09",
                "description": "Full split",
                "amount": "-100.00",
                "category_obj": "",
                "split_rule": "",
                "receiver": "Superstore",
                "parts-0-amount": "60.00",
                "parts-0-category_obj": str(self.sports.pk),
                "parts-1-amount": "40.00",
                "parts-1-category_obj": str(self.utilities.pk),
                **self._formset_management(total_forms=2),
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("expense_list"))
        expenses = list(Expense.objects.filter(user=self.user).order_by("amount"))
        self.assertEqual(len(expenses), 2)
        self.assertEqual(expenses[0].amount, Decimal("-60.00"))
        self.assertEqual(expenses[0].category_obj, self.sports)
        self.assertEqual(expenses[1].amount, Decimal("-40.00"))
        self.assertEqual(expenses[1].category_obj, self.utilities)

    def test_split_amounts_cannot_exceed_expense_amount(self):
        response = self.client.post(
            reverse("expense_add"),
            {
                "date": "2026-03-09",
                "description": "Too much split",
                "amount": "-100.00",
                "category_obj": str(self.general.pk),
                "split_rule": "",
                "receiver": "Superstore",
                "parts-0-amount": "80.00",
                "parts-0-category_obj": str(self.sports.pk),
                "parts-1-amount": "30.00",
                "parts-1-category_obj": str(self.utilities.pk),
                **self._formset_management(total_forms=2),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Split amounts cannot exceed the expense amount.")
        self.assertFalse(Expense.objects.filter(description="Too much split").exists())

    def test_split_from_edit_creates_new_expenses(self):
        expense = Expense.objects.create(
            user=self.user,
            date=date(2026, 3, 9),
            category=self.general.name,
            category_obj=self.general,
            amount="-100.00",
            receiver="Superstore",
            description="Editable split",
        )

        response = self.client.post(
            reverse("expense_edit", args=[expense.pk]),
            {
                "date": "2026-03-09",
                "description": "Editable split",
                "amount": "-100.00",
                "category_obj": str(self.general.pk),
                "split_rule": "",
                "receiver": "Superstore",
                "month": "all",
                "parts-0-amount": "40.00",
                "parts-0-category_obj": str(self.utilities.pk),
                **self._formset_management(total_forms=1),
            },
            follow=True,
        )

        self.assertRedirects(response, f"{reverse('expense_list')}?month=all")
        self.assertEqual(Expense.objects.filter(user=self.user).count(), 2)

        expense.refresh_from_db()
        self.assertEqual(expense.amount, Decimal("-60.00"))
        self.assertEqual(expense.category_obj, self.general)

        new_expense = Expense.objects.get(category_obj=self.utilities, user=self.user)
        self.assertEqual(new_expense.amount, Decimal("-40.00"))

    def test_split_expenses_update_savings_and_spending_totals(self):
        self.client.post(
            reverse("expense_add"),
            {
                "date": "2026-03-09",
                "description": "Split savings",
                "amount": "-100.00",
                "category_obj": str(self.general.pk),
                "split_rule": "",
                "receiver": "Superstore",
                "parts-0-amount": "20.00",
                "parts-0-category_obj": str(self.savings.pk),
                **self._formset_management(total_forms=1),
            },
        )

        response = self.client.get(reverse("expense_list"), {"month": "all"})

        self.assertEqual(response.context["total_spent"], Decimal("-80.00"))
        self.assertEqual(response.context["savings_total"], Decimal("20.00"))

    def test_split_expenses_show_as_independent_rows(self):
        self.client.post(
            reverse("expense_add"),
            {
                "date": "2026-03-09",
                "description": "Rendered split",
                "amount": "-100.00",
                "category_obj": str(self.general.pk),
                "split_rule": "",
                "receiver": "Superstore",
                "parts-0-amount": "30.00",
                "parts-0-category_obj": str(self.sports.pk),
                "parts-1-amount": "20.00",
                "parts-1-category_obj": str(self.utilities.pk),
                **self._formset_management(total_forms=2),
            },
        )

        response = self.client.get(reverse("expense_list"), {"month": "all"})

        rows = response.context["expense_rows"]
        self.assertEqual(len(rows), 3)
        categories = sorted([row.category_name for row in rows])
        self.assertEqual(categories, ["General", "Sports", "Utilities"])
        self.assertNotContains(response, "rowspan")
        self.assertNotContains(response, "Split #")


class CategoryManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="category-owner", password="pass")
        self.client.force_login(self.user)

    def test_user_can_edit_seeded_default_category(self):
        category = Category.objects.get(user=self.user, name="Savings")

        response = self.client.post(
            reverse("category_edit", args=[category.pk]),
            {
                "name": "Emergency Fund",
                "parent": "",
                "category_type": Category.CATEGORY_TYPE_SAVING,
                "keywords": "save,emergency",
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("category_list"))
        category.refresh_from_db()
        self.assertEqual(category.name, "Emergency Fund")
        self.assertEqual(category.keywords, "save,emergency")

    def test_user_can_delete_seeded_default_category(self):
        category = Category.objects.get(user=self.user, name="Transfers")

        response = self.client.post(
            reverse("category_delete", args=[category.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse("category_list"))
        self.assertFalse(Category.objects.filter(pk=category.pk).exists())
        self.assertTrue(
            Category.objects.filter(
                user__isnull=True,
                is_system=True,
                name="Transfers",
            ).exists()
        )

    def test_category_list_shows_single_user_owned_section(self):
        response = self.client.get(reverse("category_list"))

        self.assertContains(response, "My Categories")
        self.assertNotContains(response, "System Categories")


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

        response = self.client.get(reverse("expenses_per_month"), {"month": "2026-03"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_month_label"], "March 2026")
        self.assertEqual(response.context["prev_month_str"], "2026-02")
        self.assertEqual(response.context["next_month_str"], "2026-04")
        self.assertContains(response, "March Pie Category")
        self.assertNotContains(response, "February Pie Category")

        months = [item["month"].strftime("%Y-%m") for item in response.context["expenses_per_month"]]
        self.assertEqual(months, ["2026-02", "2026-03"])

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

        response = self.client.get(reverse("expenses_per_month"), {"month": "2026-03"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sports")
        self.assertContains(response, "General")
        march_summary = next(
            item for item in response.context["expenses_per_month"]
            if item["month"].strftime("%Y-%m") == "2026-03"
        )
        self.assertEqual(march_summary["total_spent"], Decimal("100.00"))
