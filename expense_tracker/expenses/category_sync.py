"""Apply Django keyword matches and keep the latest outcome in this session."""

from uuid import uuid4

from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from .helpers import CategorizationMatch, categorize_from_sources
from .models import Category, Expense

PREVIEW_LIMIT = 50
SESSION_KEY = "category_sync_result"


def _match(expense: Expense, user: User) -> CategorizationMatch:
    return categorize_from_sources(
        ("receiver", expense.receiver),
        ("description", expense.description),
        ("category", expense.category),
        user=user,
    )


def _preview(expense: Expense) -> dict:
    return {
        "id": expense.pk,
        "date": expense.date.isoformat(),
        "receiver": expense.receiver,
        "description": expense.description,
        "amount": str(expense.amount),
    }


def _assign(expense: Expense, category: Category) -> None:
    expense.category_obj = category
    expense.category = category.name
    expense.save(update_fields=["category_obj", "category"])


@transaction.atomic
def run_category_sync(user: User) -> dict:
    expenses = Expense.objects.filter(user=user).order_by("pk")
    counts = dict.fromkeys(
        (
            "uncategorized_before",
            "newly_categorized",
            "upgraded",
            "still_uncategorized",
        ),
        0,
    )
    rows = {
        group: [] for group in ("newly_categorized", "upgraded", "still_uncategorized")
    }

    def record(group: str, expense: Expense, **details) -> None:
        counts[group] += 1
        if len(rows[group]) < PREVIEW_LIMIT:
            rows[group].append({**_preview(expense), **details})

    for expense in (
        expenses.filter(category_obj__isnull=True)
        .select_related("split_rule")
        .iterator()
    ):
        counts["uncategorized_before"] += 1
        match = _match(expense, user)
        if match.category is None:
            record("still_uncategorized", expense)
        else:
            _assign(expense, match.category)
            record(
                "newly_categorized",
                expense,
                category=match.category.name,
                matched_keyword=match.keyword,
                matched_from=match.source,
            )

    # Keep the legacy order: reconsider categorized rows after filling in missing
    # categories. Only a deeper match under the same top-level category can move a row.
    for expense in (
        expenses.filter(category_obj__user=user)
        .select_related(
            "category_obj__parent__parent__parent__parent",
            "split_rule",
        )
        .iterator()
    ):
        current = expense.category_obj
        match = _match(expense, user)
        candidate = match.category
        if (
            candidate is None
            or candidate.get_depth() <= current.get_depth()
            or candidate.get_root().pk != current.get_root().pk
        ):
            continue
        _assign(expense, candidate)
        record(
            "upgraded",
            expense,
            old_category=current.name,
            new_category=candidate.name,
            matched_keyword=match.keyword,
            matched_from=match.source,
        )

    return {
        "id": uuid4().hex,
        "completed_at": timezone.now().isoformat(),
        "counts": counts,
        "previews": {
            group: {"rows": preview, "omitted": counts[group] - len(preview)}
            for group, preview in rows.items()
        },
    }


def record_category_sync(request: HttpRequest) -> dict:
    result = run_category_sync(request.user)
    request.session[SESSION_KEY] = {"user_id": request.user.pk, "result": result}
    return result


def latest_category_sync(request: HttpRequest) -> dict | None:
    stored = request.session.get(SESSION_KEY)
    if stored is not None and stored["user_id"] == request.user.pk:
        return stored["result"]
    return None
