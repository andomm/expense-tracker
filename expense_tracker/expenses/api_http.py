"""Shared same-origin JSON request and error handling."""

import json
from functools import wraps

from django.core.exceptions import RequestDataTooBig
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.csrf import csrf_failure as html_csrf_failure
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_cookie


class MalformedRequest(ValueError):
    pass


def api_error(
    code: str, message: str, status: int, *, fields: dict[str, list[str]] | None = None
) -> JsonResponse:
    body = {"code": code, "message": message}
    if fields:
        body["fields"] = fields
    return JsonResponse(body, status=status)


def json_endpoint(*methods: str, login_required: bool = True):
    allowed = (*methods, "HEAD") if "GET" in methods else methods

    def decorate(view):
        @never_cache
        @vary_on_cookie
        @wraps(view)
        def respond(request: HttpRequest, *args, **kwargs) -> JsonResponse:
            if request.method not in allowed:
                response = api_error("method_not_allowed", "Method not allowed.", 405)
                response.headers["Allow"] = ", ".join(allowed)
                return response
            if login_required:
                if not request.user.is_authenticated:
                    return api_error("sign_in_required", "Sign in to continue.", 401)
                # A stale tab must not use another account's session. This is a
                # precondition only; the session user still owns every request.
                expected_user = request.headers.get("X-Expense-Pilot-User")
                if expected_user is not None and expected_user != str(request.user.pk):
                    return api_error("session_changed", "Your session changed.", 401)
            try:
                return view(request, *args, **kwargs)
            except MalformedRequest as error:
                return api_error("invalid_request", str(error), 400)

        return respond

    return decorate


def json_object(request: HttpRequest) -> dict:
    if request.content_type != "application/json":
        raise MalformedRequest("Send a JSON object.")
    try:
        value = json.loads(request.body)
    except (ValueError, RecursionError, RequestDataTooBig) as error:
        raise MalformedRequest("Send a valid JSON object.") from error
    if not isinstance(value, dict):
        raise MalformedRequest("Send a JSON object.")
    return value


@never_cache
@vary_on_cookie
def _api_csrf_failure(request: HttpRequest) -> JsonResponse:
    return api_error("csrf_failed", "Could not verify this request.", 403)


def csrf_failure(request: HttpRequest, reason: str = "") -> HttpResponse:
    if request.resolver_match and request.resolver_match.namespace == "api":
        return _api_csrf_failure(request)
    return html_csrf_failure(request, reason=reason)
