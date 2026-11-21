"""Run an atomic CSV import and expose its latest successful session report."""

from uuid import uuid4

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from .helpers import categorize_from_sources
from .importers import CSVError, get_importer
from .models import Expense

PREVIEW_LIMIT = 50
DESCRIPTION_PREVIEW_LENGTH = 200
SESSION_KEY = "csv_import_result"


@transaction.atomic
def _run_import(user: User, import_format: str, file) -> dict:
    total = categorized = 0
    preview = []
    for line, parsed in get_importer(import_format).rows(file):
        try:
            Expense._meta.get_field("amount").run_validators(parsed.amount)
        except ValidationError:
            raise CSVError(
                "Use an amount with up to eight whole digits and two decimal places.",
                row=line,
            ) from None
        for field, value in (
            ("category", parsed.category),
            ("receiver", parsed.receiver),
        ):
            limit = Expense._meta.get_field(field).max_length
            if len(value) > limit:
                raise CSVError(
                    f"The {field} must be {limit} characters or fewer.", row=line
                )
        if any(
            "\0" in value
            for value in (parsed.receiver, parsed.description, parsed.category)
        ):
            raise CSVError("Text fields cannot contain null characters.", row=line)

        match = categorize_from_sources(
            ("receiver", parsed.receiver),
            ("description", parsed.description),
            ("category", parsed.category),
            user=user,
        )
        expense = Expense.objects.create(
            user=user,
            date=parsed.date,
            category=parsed.category,
            category_obj=match.category,
            description=parsed.description,
            amount=parsed.amount,
            receiver=parsed.receiver,
        )
        total += 1
        if match.category is not None:
            categorized += 1
        elif len(preview) < PREVIEW_LIMIT:
            description = parsed.description
            if len(description) > DESCRIPTION_PREVIEW_LENGTH:
                description = description[: DESCRIPTION_PREVIEW_LENGTH - 1] + "…"
            preview.append(
                {
                    "id": expense.pk,
                    "date": parsed.date.isoformat(),
                    "receiver": parsed.receiver,
                    "description": description,
                    "amount": format(parsed.amount, ".2f"),
                }
            )

    if not total:
        raise CSVError("The file has no transactions to import.")
    uncategorized = total - categorized
    return {
        "id": uuid4().hex,
        "completed_at": timezone.now().isoformat(),
        "counts": {
            "total": total,
            "categorized": categorized,
            "uncategorized": uncategorized,
        },
        "uncategorized_preview": {
            "rows": preview,
            "omitted": uncategorized - len(preview),
        },
    }


def record_import(request: HttpRequest, *, import_format: str, file) -> dict:
    result = _run_import(request.user, import_format, file)
    request.session[SESSION_KEY] = {"user_id": request.user.pk, "result": result}
    return result


def latest_import(request: HttpRequest) -> dict | None:
    stored = request.session.get(SESSION_KEY)
    if stored is None or stored["user_id"] != request.user.pk:
        return None

    result = stored["result"]
    preview = result["uncategorized_preview"]
    editable = set(
        Expense.objects.filter(
            user=request.user, pk__in=[row["id"] for row in preview["rows"]]
        ).values_list("pk", flat=True)
    )
    return {
        **result,
        "uncategorized_preview": {
            **preview,
            "rows": [
                {
                    **row,
                    "edit_url": reverse("expense_edit", args=[row["id"]])
                    if row["id"] in editable
                    else None,
                }
                for row in preview["rows"]
            ],
        },
    }
