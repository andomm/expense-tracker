from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from .forms import BaseSplitRowFormSet, ExpenseForm
from .models import Expense


def validate_expense(form: ExpenseForm, splits: BaseSplitRowFormSet) -> bool:
    valid_form = form.is_valid()
    splits.total_amount = (
        abs(form.cleaned_data["amount"]) if "amount" in form.cleaned_data else None
    )
    valid_splits = splits.is_valid()
    if not valid_form or not valid_splits:
        return False
    if (
        splits.split_total < splits.total_amount
        and not form.cleaned_data["category_obj"]
    ):
        form.add_error(
            "category_obj",
            "Select a category for the remaining amount or split the full expense.",
        )
        return False
    return True


@dataclass(frozen=True)
class SavedExpenses:
    expense_ids: list[int]
    retained_id: int | None


def signed_part(amount: Decimal, magnitude: Decimal) -> Decimal:
    return -magnitude if amount < 0 else magnitude


@transaction.atomic
def save_expense(
    form: ExpenseForm, splits: BaseSplitRowFormSet, *, clear_category: bool = False
) -> SavedExpenses:
    expense = form.save(commit=False, clear_category=clear_category)
    if not splits.parts:
        expense.save()
        return SavedExpenses([expense.pk], expense.pk)

    amount = expense.amount
    remainder = abs(amount) - splits.split_total
    retained_id = None
    if remainder:
        expense.amount = signed_part(amount, remainder)
        expense.user_share = None
        expense.save()
        retained_id = expense.pk

    part_ids = [
        Expense.objects.create(
            user=expense.user,
            date=expense.date,
            description=expense.description,
            amount=signed_part(amount, magnitude),
            category_obj=category,
            category=category.name,
            split_rule=expense.split_rule,
            receiver=expense.receiver,
        ).pk
        for magnitude, category in splits.parts
    ]
    if retained_id is not None:
        return SavedExpenses([retained_id, *part_ids], retained_id)
    if expense.pk:
        expense.delete()
    return SavedExpenses(part_ids, None)
