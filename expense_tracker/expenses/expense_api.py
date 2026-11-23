from dataclasses import asdict
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.forms.utils import ErrorDict
from django.http import HttpRequest, JsonResponse

from .api_http import MalformedRequest, api_error, json_endpoint, json_object
from .expense_save import save_expense, signed_part, validate_expense
from .forms import (
    BaseSplitRowFormSet,
    ExpenseForm,
    SplitRowFormSet,
    build_category_choices,
    get_user_category_queryset,
)
from .models import Expense, ExpenseSplitRule


@json_endpoint("GET")
def expense_form_options(request: HttpRequest) -> JsonResponse:
    categories = build_category_choices(get_user_category_queryset(request.user))
    rules = ExpenseSplitRule.objects.filter(user=request.user).order_by("name", "pk")
    return JsonResponse(
        {
            "categories": [{"id": int(pk), "label": label} for pk, label in categories],
            "share_rules": [{"id": rule.pk, "label": str(rule)} for rule in rules],
            "max_splits": SplitRowFormSet.max_num,
        }
    )


@json_endpoint("GET", "POST")
def expense_delete_all(request: HttpRequest) -> JsonResponse:
    expenses = Expense.objects.filter(user=request.user)
    if request.method != "POST":
        return JsonResponse({"count": expenses.count()})

    if json_object(request).get("confirmation") != "DELETE":
        return api_error("validation_failed", "Type DELETE exactly to continue.", 422)

    _, counts = expenses.delete()
    count = counts.get(Expense._meta.label, 0)
    messages.success(
        request,
        f"Deleted {count} expense{'s' if count != 1 else ''}."
        if count
        else "No expenses to delete.",
    )
    return JsonResponse({"deleted_count": count})


def _not_found() -> JsonResponse:
    return api_error("not_found", "This expense was not found.", 404)


@json_endpoint("GET", "PUT", "DELETE")
def expense_detail(request: HttpRequest, pk: int) -> JsonResponse:
    expenses = Expense.objects.filter(user=request.user, pk=pk)
    if request.method == "DELETE":
        _, counts = expenses.delete()
        if not counts.get(Expense._meta.label):
            return _not_found()
        messages.success(request, "Expense deleted.")
        return JsonResponse({"deleted_count": 1})
    if request.method == "PUT":
        with transaction.atomic():
            expense = expenses.select_for_update().first()
            return _save(request, expense, status=200) if expense else _not_found()

    expense = expenses.select_related("category_obj", "split_rule").first()
    if not expense:
        return _not_found()
    return JsonResponse(
        {
            "id": expense.pk,
            "date": expense.date.isoformat(),
            "receiver": expense.receiver,
            "description": expense.description,
            "amount": f"{expense.get_source_amount():.2f}",
            "personal_share": f"{expense.get_effective_user_amount():.2f}",
            "category_id": _owned_id(expense.category_obj, expense.user_id),
            "share_rule_id": _owned_id(expense.split_rule, expense.user_id),
        }
    )


def _owned_id(relation, user_id: int) -> int | None:
    return relation.pk if relation and relation.user_id == user_id else None


def create_expense(request: HttpRequest) -> JsonResponse:
    return _save(request, Expense(user=request.user), status=201)


def _bind_forms(
    data: dict, expense: Expense, *, preview: bool = False
) -> tuple[ExpenseForm, BaseSplitRowFormSet]:
    def text(source: dict, name: str) -> str:
        value = source.get(name, "")
        if not isinstance(value, str):
            raise MalformedRequest(f"{name} must be a string.")
        return value

    def choice(source: dict, name: str) -> int | None:
        value = source.get(name)
        if value is not None and type(value) is not int:
            raise MalformedRequest(f"{name} must be an ID or null.")
        return value

    rows = data.get("splits", [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise MalformedRequest("splits must be a list of objects.")
    if len(rows) > SplitRowFormSet.max_num:
        raise MalformedRequest(f"Send at most {SplitRowFormSet.max_num} split rows.")

    row_data = {
        "parts-TOTAL_FORMS": len(rows),
        # An explicitly submitted row is never an unused extra form.
        "parts-INITIAL_FORMS": len(rows),
    }
    for index, row in enumerate(rows):
        row_data[f"parts-{index}-amount"] = text(row, "amount")
        row_data[f"parts-{index}-category_obj"] = choice(row, "category_id")

    kwargs = {"user": expense.user}
    fields = (
        {}
        if preview
        else {name: text(data, name) for name in ("date", "receiver", "description")}
    )
    form = ExpenseForm(
        {
            **fields,
            "amount": text(data, "amount"),
            "category_obj": choice(data, "category_id"),
            "split_rule": choice(data, "share_rule_id"),
        },
        instance=expense,
        **kwargs,
    )
    return form, SplitRowFormSet(row_data, prefix="parts", form_kwargs=kwargs)


_FIELD_NAMES = {
    "category_obj": "category_id",
    "split_rule": "share_rule_id",
    "__all__": "form",
}


def _field_messages(errors: ErrorDict) -> dict[str, list[str]]:
    return {
        _FIELD_NAMES.get(name, name): list(values) for name, values in errors.items()
    }


def _save(request: HttpRequest, expense: Expense, *, status: int) -> JsonResponse:
    form, splits = _bind_forms(json_object(request), expense)
    valid = validate_expense(form, splits)
    if valid and _personal_share(form, splits) is None:
        form.add_error(
            "split_rule", "The selected rule makes a personal share too large."
        )
        valid = False
    if not valid:
        errors = _field_messages(form.errors)
        if splits.non_form_errors():
            errors["splits"] = list(splits.non_form_errors())
        for index, row in enumerate(splits.errors):
            errors.update(
                {
                    f"splits[{index}].{key}": value
                    for key, value in _field_messages(row).items()
                }
            )
        return api_error(
            "validation_failed", "Check the highlighted fields.", 422, fields=errors
        )

    result = save_expense(form, splits, clear_category=True)
    count = len(result.expense_ids)
    messages.success(
        request, "Expense saved." if count == 1 else f"Saved {count} expenses."
    )
    return JsonResponse(asdict(result), status=status)


def _personal_share(form: ExpenseForm, splits: BaseSplitRowFormSet) -> Decimal | None:
    data = form.cleaned_data
    amount = data["amount"]
    rule = data["split_rule"]
    if splits.parts:
        magnitudes = [value for value, _ in splits.parts]
        remainder = abs(amount) - splits.split_total
        if remainder:
            magnitudes.append(remainder)
        sources = [
            Expense(amount=signed_part(amount, value), split_rule=rule)
            for value in magnitudes
        ]
    else:
        sources = [
            Expense(amount=amount, split_rule=rule, user_share=form.instance.user_share)
        ]

    # The stored share rounds per independent expense, not once for the full amount.
    shares = [source.share_for_save().quantize(Decimal("0.01")) for source in sources]
    if any(abs(value) > Decimal("99999999.99") for value in shares):
        return None
    return sum(shares, Decimal(0))


@json_endpoint("POST")
def expense_preview(request: HttpRequest, pk: int | None = None) -> JsonResponse:
    """Calculate a draft's figures without writing or putting its amounts in the URL."""
    expense = (
        Expense(user=request.user)
        if pk is None
        else (Expense.objects.filter(user=request.user, pk=pk).first())
    )
    if expense is None:
        return _not_found()
    form, splits = _bind_forms(json_object(request), expense, preview=True)
    validate_expense(form, splits)
    data = form.cleaned_data
    amount = data.get("amount")
    parts_valid = not any(splits.errors) and not splits.management_form.errors
    total = splits.split_total if parts_valid else None
    remainder = (
        abs(amount) - total if amount is not None and total is not None else None
    )
    share = None
    if remainder is not None and remainder >= 0 and "split_rule" in data:
        share = _personal_share(form, splits)
    return JsonResponse(
        {
            "amount": _money(amount),
            "split_total": _money(total),
            "remaining": _money(remainder),
            "personal_share": _money(share),
        }
    )


def _money(value: Decimal | None) -> str | None:
    return f"{value:.2f}" if value is not None else None
