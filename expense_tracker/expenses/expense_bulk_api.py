"""Confirm an Expenses selection and apply one atomic bulk action to it."""

import json
import re
from datetime import timedelta
from hashlib import sha256
from itertools import batched
from secrets import token_hex
from sqlite3 import SQLITE_BUSY, SQLITE_LOCKED

from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.db import OperationalError, transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone

from .api_http import MalformedRequest, api_error, json_endpoint, json_object
from .expense_list import ExpenseFilters, read_expense_list
from .forms import SortForm
from .models import Category, Expense

FILTER_KEYS = {"month", "search", "category_filter", "order_by"}
CONFIRMATION_LIFETIME = timedelta(minutes=10)


def _filtered_ids(user: User, params: dict) -> list[int] | None:
    form = SortForm(params, user=user)
    filters = ExpenseFilters.from_params(params, form)
    if not form.is_valid() or filters.period != params["month"]:
        return None
    return sorted(
        row.expense.pk for row in read_expense_list(user, filters, form.categories).rows
    )


def _membership(ids: list[int]) -> str:
    return sha256(json.dumps(ids).encode()).hexdigest()


def _stale_selection() -> JsonResponse:
    return api_error(
        "stale_selection", "The selection changed or expired. Confirm it again.", 409
    )


def _valid_id(value: object) -> bool:
    return type(value) is int and 0 < value < 2**63


def _explicit_ids(value: object) -> list[int]:
    if not isinstance(value, list) or not value or not all(map(_valid_id, value)):
        raise MalformedRequest("Send a nonempty list of expense IDs.")
    return sorted(set(value))


def _all_owned(user: User, ids: list[int]) -> bool:
    owned = Expense.objects.filter(user=user)
    return all(
        owned.filter(pk__in=chunk).count() == len(chunk) for chunk in batched(ids, 500)
    )


@json_endpoint("POST")
def confirm(request: HttpRequest) -> JsonResponse:
    data = json_object(request)
    params = data.get("filters")
    if data.keys() == {"ids"}:
        ids = _explicit_ids(data["ids"])
        if not _all_owned(request.user, ids):
            return api_error(
                "not_found", "Some selected expenses are unavailable.", 404
            )
    elif (
        data.keys() == {"filters"}
        and isinstance(params, dict)
        and params.keys() == FILTER_KEYS
        and all(isinstance(value, str) for value in params.values())
    ):
        ids = _filtered_ids(request.user, params)
        if ids is None:
            return _stale_selection()
        if not ids:
            return JsonResponse({"count": 0, "token": None})
    else:
        raise MalformedRequest(
            "Send either expense IDs or the current expense filters."
        )

    # Short-lived confirmation records use Django's existing session table and
    # clearsessions cleanup. These keys are not login sessions or cookies.
    key = "bulk-" + token_hex(16)
    Session.objects.create(
        session_key=key,
        session_data=SessionStore().encode(
            {
                "owner": request.user.pk,
                "session": request.session.session_key,
                "filters": params,
                "membership": _membership(ids),
            }
        ),
        expire_date=timezone.now() + CONFIRMATION_LIFETIME,
    )
    return JsonResponse({"count": len(ids), "token": key})


@json_endpoint("POST")
def apply(request: HttpRequest, *, recategorize: bool = False) -> JsonResponse:
    data = json_object(request)
    token = data.get("token")
    if not isinstance(token, str) or not re.fullmatch(r"bulk-[0-9a-f]{32}", token):
        raise MalformedRequest("Send a selection confirmation token.")
    requested_ids = _explicit_ids(data["ids"]) if "ids" in data else None
    category_id = data.get("category_id")
    if recategorize and not _valid_id(category_id):
        raise MalformedRequest("Send a destination category ID.")

    try:
        with transaction.atomic():
            record = (
                Session.objects.select_for_update()
                .filter(session_key=token, expire_date__gt=timezone.now())
                .first()
            )
            if record is None:
                return _stale_selection()
            confirmed = record.get_decoded()
            if (
                confirmed.get("owner") != request.user.pk
                or confirmed.get("session") != request.session.session_key
            ):
                return _stale_selection()
            params = confirmed["filters"]
            if (params is None) != (requested_ids is not None):
                return _stale_selection()
            ids = (
                requested_ids if params is None else _filtered_ids(request.user, params)
            )
            if (
                not ids
                or _membership(ids) != confirmed["membership"]
                or (params is None and not _all_owned(request.user, ids))
            ):
                record.delete()
                return _stale_selection()

            category = None
            if recategorize:
                category = Category.objects.filter(
                    user=request.user, pk=category_id
                ).first()
                if category is None:
                    return api_error(
                        "validation_failed",
                        "Choose one of your categories.",
                        422,
                        fields={"category_id": ["This category is unavailable."]},
                    )

            # Consumption and mutation commit together: a successful write
            # cannot reuse its confirmation, even if the membership is unchanged.
            record.delete()
            owned = Expense.objects.filter(user=request.user)
            for chunk in batched(ids, 500):
                selected = owned.filter(pk__in=chunk)
                if category is None:
                    selected.delete()
                else:
                    selected.update(category_obj=category, category=category.name)
            return JsonResponse({"affected_count": len(ids)})
    except OperationalError as error:
        # SQLite cannot upgrade a stale read snapshot to a write transaction.
        # Roll back and ask for confirmation instead of retrying the mutation.
        code = getattr(error.__cause__, "sqlite_errorcode", 0)
        if code & 0xFF in {SQLITE_BUSY, SQLITE_LOCKED}:
            return _stale_selection()
        raise
