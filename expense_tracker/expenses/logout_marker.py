"""Distinguish an explicit Django logout from session expiry across tabs."""

from secrets import token_urlsafe

from django.conf import settings
from django.http import HttpRequest

LOGOUT_COOKIE = "expense_signed_out"


def record_logout(sender, request: HttpRequest | None, **kwargs) -> None:
    if request is not None:
        request.expense_logout_marker = token_urlsafe(16)


def logout_marker(request: HttpRequest) -> str | None:
    return getattr(request, "expense_logout_marker", request.COOKIES.get(LOGOUT_COOKIE))


def logout_marker_middleware(get_response):
    def middleware(request):
        response = get_response(request)
        if marker := getattr(request, "expense_logout_marker", None):
            # This random marker carries no identity or privileges.
            response.set_cookie(
                LOGOUT_COOKIE,
                marker,
                httponly=True,
                samesite="Lax",
                secure=settings.SESSION_COOKIE_SECURE,
            )
        return response

    return middleware
