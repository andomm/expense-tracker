from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from .forms import BaseSplitRowFormSet, ExpenseForm
from .models import Category, Expense, ExpenseSplitRule


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


@dataclass(frozen=True)
class ExpenseLine:
    amount: Decimal
    category: Category | None
    existing_share: Decimal | None = None

    def apply(self, expense: Expense) -> Expense:
        expense.amount = self.amount
        expense.category_obj = self.category
        expense.category = self.category.name if self.category else ""
        expense.user_share = self.existing_share
        return expense


@dataclass(frozen=True)
class ExpensePlan:
    retained: ExpenseLine | None
    parts: tuple[ExpenseLine, ...]
    rule: ExpenseSplitRule | None

    def personal_share(self) -> Decimal | None:
        lines = (self.retained, *self.parts) if self.retained else self.parts
        # The stored share rounds per independent expense, not per original total.
        shares = [
            line.apply(Expense(split_rule=self.rule))
            .share_for_save()
            .quantize(Decimal("0.01"))
            for line in lines
        ]
        if any(abs(share) > Decimal("99999999.99") for share in shares):
            return None
        return sum(shares, Decimal(0))


def plan_expense(form: ExpenseForm, splits: BaseSplitRowFormSet) -> ExpensePlan:
    """Build signed rows from validated amounts and split choices."""
    data = form.cleaned_data
    amount, rule = data["amount"], data["split_rule"]
    category = data.get("category_obj")  # Preview can run without a main category.
    parts = splits.parts
    if not parts:
        return ExpensePlan(
            ExpenseLine(amount, category, form.instance.user_share), (), rule
        )

    sign = -1 if amount < 0 else 1
    remainder = abs(amount) - splits.split_total
    return ExpensePlan(
        ExpenseLine(sign * remainder, category) if remainder else None,
        tuple(
            ExpenseLine(sign * magnitude, part_category)
            for magnitude, part_category in parts
        ),
        rule,
    )


@transaction.atomic
def save_expense(form: ExpenseForm, plan: ExpensePlan) -> SavedExpenses:
    expense = form.save(commit=False)
    ids = []
    retained_id = None
    if plan.retained:
        plan.retained.apply(expense).save()
        retained_id = expense.pk
        ids.append(retained_id)

    for part in plan.parts:
        row = part.apply(
            Expense(
                user=expense.user,
                date=expense.date,
                description=expense.description,
                split_rule=plan.rule,
                receiver=expense.receiver,
            )
        )
        row.save(force_insert=True)
        ids.append(row.pk)
    if retained_id is None and expense.pk:
        expense.delete()
    return SavedExpenses(ids, retained_id)
