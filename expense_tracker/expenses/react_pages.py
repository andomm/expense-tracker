from collections.abc import Callable
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe


@login_required
@never_cache
@require_safe
def react_host(request: HttpRequest, screen: str) -> HttpResponse:
    return render(
        request,
        "react_host.html",
        {
            "vite_origin": settings.VITE_DEV_ORIGIN,
            "app": {
                "screen": screen,
                "urls": {
                    "expenses": reverse("expense_list"),
                    "analytics": reverse("expenses_per_month"),
                    "categories": reverse("category_list"),
                    "upload": reverse("upload_csv"),
                    "login": reverse("login"),
                    "logout": reverse("logout"),
                    "sessionApi": reverse("api:session"),
                    "expensesApi": reverse("api:expenses"),
                },
            },
        },
    )


def pilot_page(screen: str, legacy: Callable[[HttpRequest], HttpResponse]):
    """Opt a named Django page into the local React pilot, never a URL prefix."""

    @wraps(legacy)
    def view(request: HttpRequest) -> HttpResponse:
        if settings.DEBUG and settings.REACT_EXPENSES_PILOT:
            return react_host(request, screen)
        return legacy(request)

    return view
