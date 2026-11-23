from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.http import HttpRequest, JsonResponse
from django.middleware.csrf import get_token, rotate_token
from django.shortcuts import resolve_url
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .api_http import MalformedRequest, api_error, json_endpoint, json_object
from .logout_marker import logout_marker


def _session_data(request: HttpRequest) -> dict:
    user = request.user
    return {
        "user": {"id": user.pk, "username": user.get_username()}
        if user.is_authenticated
        else None,
        "csrf_token": get_token(request),
        "logout_marker": logout_marker(request),
    }


@json_endpoint("GET", login_required=False)
def session_status(request: HttpRequest) -> JsonResponse:
    return JsonResponse(_session_data(request))


def safe_return_url(value: object) -> str:
    # Always return a local path, even if the request host is also an allowed host.
    if (
        isinstance(value, str)
        and value.startswith("/")
        and not value.startswith("//")
        and "\\" not in value
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
        and url_has_allowed_host_and_scheme(value, allowed_hosts=set())
    ):
        return value
    return resolve_url(settings.LOGIN_REDIRECT_URL)


def _authenticate(request: HttpRequest, *, signup: bool) -> JsonResponse:
    data = json_object(request)
    expected = request.headers.get("X-Expense-Pilot-User")
    current = str(request.user.pk) if request.user.is_authenticated else "anonymous"
    if expected is not None and expected != current:
        return api_error("session_changed", "Your session changed.", 401)

    fields = (
        ("username", "password1", "password2") if signup else ("username", "password")
    )
    credentials = {name: data.get(name, "") for name in fields}
    if not all(isinstance(value, str) for value in credentials.values()):
        raise MalformedRequest("Credentials must be text.")
    form = (
        UserCreationForm(credentials)
        if signup
        else AuthenticationForm(request, credentials)
    )
    if not form.is_valid():
        errors = {
            "form" if name == "__all__" else name: list(messages)
            for name, messages in form.errors.items()
        }
        message = (
            "Check your account details." if signup else "Check your sign-in details."
        )
        return api_error("validation_failed", message, 422, fields=errors)

    login(request, form.save() if signup else form.get_user())
    return JsonResponse(
        {**_session_data(request), "next": safe_return_url(data.get("next"))},
        status=201 if signup else 200,
    )


@json_endpoint("POST", login_required=False)
def sign_in(request: HttpRequest) -> JsonResponse:
    return _authenticate(request, signup=False)


@json_endpoint("POST", login_required=False)
def sign_up(request: HttpRequest) -> JsonResponse:
    return _authenticate(request, signup=True)


@json_endpoint("POST")
def sign_out(request: HttpRequest) -> JsonResponse:
    json_object(request)
    logout(request)
    rotate_token(request)
    return JsonResponse({**_session_data(request), "next": reverse("login")})
