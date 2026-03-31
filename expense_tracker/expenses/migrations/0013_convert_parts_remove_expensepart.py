from decimal import Decimal

from django.db import migrations


def convert_parts_to_expenses(apps, schema_editor):
    """Convert existing ExpensePart records into independent Expense records."""
    Expense = apps.get_model("expenses", "Expense")
    ExpensePart = apps.get_model("expenses", "ExpensePart")
    Category = apps.get_model("expenses", "Category")

    processed_expense_ids = set()

    for part in ExpensePart.objects.all().order_by("expense_id", "order", "pk"):
        expense = Expense.objects.get(pk=part.expense_id)
        cat_name = ""
        if part.category_obj_id:
            try:
                cat_name = Category.objects.get(pk=part.category_obj_id).name
            except Category.DoesNotExist:
                pass

        sign = Decimal("-1") if expense.amount < 0 else Decimal("1")
        new_amount = sign * part.amount

        Expense.objects.create(
            user_id=expense.user_id,
            date=expense.date,
            category=cat_name,
            category_obj_id=part.category_obj_id,
            description=expense.description,
            amount=new_amount,
            user_share=new_amount,
            split_rule_id=expense.split_rule_id,
            receiver=expense.receiver,
        )

        processed_expense_ids.add(expense.pk)

    for expense_id in processed_expense_ids:
        expense = Expense.objects.get(pk=expense_id)
        parts_total = sum(
            p.amount
            for p in ExpensePart.objects.filter(expense_id=expense_id)
        )
        sign = Decimal("-1") if expense.amount < 0 else Decimal("1")
        remainder = abs(expense.amount) - parts_total

        if remainder > Decimal("0"):
            expense.amount = sign * remainder
            expense.user_share = sign * remainder
            expense.save()
        else:
            expense.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("expenses", "0012_expensepart"),
    ]

    operations = [
        migrations.RunPython(
            convert_parts_to_expenses,
            migrations.RunPython.noop,
        ),
        migrations.DeleteModel(
            name="ExpensePart",
        ),
    ]
