from datetime import date

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class UserOwnedDefaultCategoryMigrationTests(TransactionTestCase):
    migrate_from = ("expenses", "0010_category_income_type")
    migrate_to = ("expenses", "0011_user_owned_default_categories")

    def setUp(self):
        super().setUp()

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps

        User = old_apps.get_model("auth", "User")
        Category = old_apps.get_model("expenses", "Category")
        Expense = old_apps.get_model("expenses", "Expense")

        user = User.objects.create(username="migrated-user")
        self.user_id = user.pk
        shared_savings = Category.objects.get(
            user__isnull=True,
            is_system=True,
            name="Savings",
        )
        Expense.objects.create(
            user_id=self.user_id,
            date=date(2026, 3, 9),
            category="Savings",
            category_obj_id=shared_savings.pk,
            amount="-10.00",
            user_share="-10.00",
            receiver="Bank transfer",
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def test_existing_system_category_expenses_are_remapped_to_user_copy(self):
        Category = self.apps.get_model("expenses", "Category")
        Expense = self.apps.get_model("expenses", "Expense")

        user_savings = Category.objects.get(user_id=self.user_id, name="Savings")
        expense = Expense.objects.get(user_id=self.user_id, receiver="Bank transfer")

        self.assertFalse(user_savings.is_system)
        self.assertEqual(expense.category_obj_id, user_savings.pk)
        self.assertEqual(expense.category, "Savings")
