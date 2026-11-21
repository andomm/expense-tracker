from collections.abc import Callable
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.messages import get_messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .models import Category, Expense


TITLES = {
    "expenses": "Expenses",
    "expense-add": "Add expense",
    "expense-edit": "Edit expense",
    "expense-delete": "Delete expense",
    "expense-delete-all": "Delete all expenses",
    "categories": "Categories",
    "category-add": "Add category",
    "category-edit": "Edit category",
    "category-delete": "Delete category",
    "category-sync": "Sync existing expenses",
    "category-sync-result": "Category sync results",
}
SYNC_SCREENS = {"category-sync", "category-sync-result"}
CATEGORY_SCREENS = {"categories", "category-add", "category-edit", "category-delete"}


@login_required
@never_cache
@require_safe
def react_host(
    request: HttpRequest, screen: str, pk: int | None = None
) -> HttpResponse:
    if pk is not None:
        model = Category if screen in CATEGORY_SCREENS else Expense
        if not model.objects.filter(user=request.user, pk=pk).exists():
            raise Http404

    app = {
        "screen": screen,
        "userId": request.user.pk,
        "urls": {
            "expenses": reverse("expense_list"),
            "addExpense": reverse("expense_add"),
            "deleteAllExpenses": reverse("expense_delete_all"),
            "analytics": reverse("expenses_per_month"),
            "categories": reverse("category_list"),
            "upload": reverse("upload_csv"),
            "login": reverse("login"),
            "logout": reverse("logout"),
            "sessionApi": reverse("api:session"),
            "expensesApi": reverse("api:expenses"),
        },
    }
    if screen == "categories":
        app["categoryList"] = {
            "api": reverse("api:categories"),
            "addUrl": reverse("category_add"),
            "syncUrl": reverse("sync_categories"),
            "syncResultUrl": reverse("sync_summary") if settings.CATEGORY_SYNC_REACT_CANDIDATE else None,
            "notices": [str(message) for message in get_messages(request)],
        }
    elif screen in SYNC_SCREENS:
        app["categorySync"] = {
            "startUrl": reverse("sync_categories"),
            "resultUrl": reverse("sync_summary"),
            "startApi": reverse("api:category-sync"),
            "latestApi": reverse("api:category-sync-latest"),
        }
    elif screen in CATEGORY_SCREENS:
        detail = reverse("api:category-detail", args=[pk]) if pk is not None else None
        app["categoryAction"] = {
            "readApi": detail or reverse("api:category-form-options"),
            "writeApi": detail or reverse("api:categories"),
        }
    elif screen == "expenses":
        app["notices"] = [str(message) for message in get_messages(request)]
    elif screen in ("expense-delete", "expense-delete-all"):
        app["deletion"] = {
            "api": (
                reverse("api:expense-detail", args=[pk])
                if pk is not None
                else reverse("api:expense-delete-all")
            ),
            "returnUrl": _list_context_url(request, "expense_list"),
        }
    else:
        args = [] if pk is None else [pk]
        app["form"] = {
            "detailApi": reverse("api:expense-detail", args=args) if args else None,
            "optionsApi": reverse("api:expense-form-options"),
            "previewApi": reverse("api:expense-preview", args=args),
            "returnUrl": _list_context_url(request, "expense_list"),
            "deleteUrl": _list_context_url(request, "expense_delete", args)
            if args
            else None,
        }

    return render(
        request,
        "react_host.html",
        {
            "vite_origin": settings.VITE_DEV_ORIGIN,
            "app": app,
            "title": TITLES[screen],
        },
    )


def _list_context_url(
    request: HttpRequest, name: str, args: list[int] | None = None
) -> str:
    params = {
        key: value
        for key in ("month", "order_by", "category_filter", "search", "page")
        if (value := request.GET.get(key))
    }
    url = reverse(name, args=args)
    return f"{url}?{urlencode(params)}" if params else url


def migrated_page(screen: str, legacy: Callable[..., HttpResponse]):
    """Serve one explicitly mapped React screen in the local dev runner."""

    @wraps(legacy)
    def view(request: HttpRequest, **kwargs) -> HttpResponse:
        if (
            settings.DEBUG and settings.LOCAL_REACT_DEV and not settings.LEGACY_PAGES
            and (screen not in SYNC_SCREENS or settings.CATEGORY_SYNC_REACT_CANDIDATE)
        ):
            return react_host(request, screen, **kwargs)
        return legacy(request, **kwargs)

    return view
