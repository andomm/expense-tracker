import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

PASSWORD = "local-synthetic-passphrase-18!"


@pytest.fixture
def browser(db):
    return Client(enforce_csrf_checks=True)


def session(browser):
    return browser.get(reverse("api:session")).json()


def auth_post(browser, action, data, token=None, **headers):
    return browser.post(
        reverse(f"api:session-{action}"),
        data,
        content_type="application/json",
        **({"HTTP_X_CSRFTOKEN": token} if token else {}),
        **headers,
    )


def test_sign_in_uses_django_session_and_rotates_csrf(browser):
    account = User.objects.create_user(username="wallet-owner", password=PASSWORD)
    path = "/expenses/?search=paper%20bag&month=all"
    old_token = session(browser)["csrf_token"]
    old_secret = browser.cookies["csrftoken"].value
    credentials = {"username": account.username, "password": PASSWORD, "next": path}

    rejected = auth_post(
        browser, "login", {**credentials, "password": "wrong"}, old_token
    )
    assert rejected.status_code == 422
    assert rejected.json()["fields"]["form"]
    assert session(browser)["user"] is None

    response = auth_post(browser, "login", credentials, old_token)
    assert response.status_code == 200
    signed_in = response.json()
    assert signed_in["user"] == {"id": account.pk, "username": account.username}
    assert signed_in["next"] == path
    assert "no-store" in response.headers["Cache-Control"]
    assert browser.cookies["csrftoken"].value != old_secret
    assert browser.get(path).wsgi_request.user == account
    assert auth_post(browser, "logout", {}, old_token).json()["code"] == "csrf_failed"
    assert browser.get(reverse("api:session-logout")).status_code == 405
    assert session(browser)["user"]["id"] == account.pk
    before_logout = browser.cookies["csrftoken"].value
    response = auth_post(browser, "logout", {}, signed_in["csrf_token"])
    assert response.status_code == 200
    assert response.json()["next"] == reverse("login")
    assert response.json()["logout_marker"] != signed_in["logout_marker"]
    assert browser.cookies["csrftoken"].value != before_logout
    assert session(browser)["user"] is None
    assert browser.get(reverse("api:expenses")).json()["code"] == "sign_in_required"


@pytest.mark.parametrize("action", ["login", "signup", "logout"])
def test_auth_post_requires_csrf_even_without_a_session(browser, action):
    session(browser)
    response = auth_post(browser, action, {})
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_signup_validates_and_signs_in(browser):
    credentials = {
        "username": "new-wallet",
        "password1": PASSWORD,
        "password2": PASSWORD,
    }
    token = session(browser)["csrf_token"]
    response = auth_post(
        browser, "signup", {**credentials, "password2": "mismatch"}, token
    )
    assert response.status_code == 422
    assert "password2" in response.json()["fields"]
    assert session(browser)["user"] is None

    response = auth_post(
        browser, "signup", {**credentials, "next": "//outside.invalid"}, token
    )
    assert response.status_code == 201
    account = response.json()["user"]
    assert account["username"] == credentials["username"]
    assert response.json()["next"] == reverse("expense_list")
    assert session(browser)["user"] == account


@pytest.mark.parametrize(
    "target",
    [
        "https://testserver/expenses/",
        "/\\outside.invalid",
        "///outside.invalid",
        "/\t/outside.invalid",
    ],
)
def test_login_rejects_nonlocal_return_paths(browser, target):
    User.objects.create_user(username="wallet-owner", password=PASSWORD)
    response = auth_post(
        browser,
        "login",
        {
            "username": "wallet-owner",
            "password": PASSWORD,
            "next": target,
        },
        session(browser)["csrf_token"],
    )
    assert response.status_code == 200
    assert response.json()["next"] == reverse("expense_list")


def test_account_switch_blocks_stale_tab_and_multipart_without_fresh_csrf(browser):
    owner = User.objects.create_user(username="wallet-owner", password=PASSWORD)
    other = User.objects.create_user(username="other-wallet", password=PASSWORD)

    def login(account, token):
        response = auth_post(
            browser,
            "login",
            {
                "username": account.username,
                "password": PASSWORD,
            },
            token,
        )
        assert response.status_code == 200
        return response.json()["csrf_token"]

    old_token = login(owner, session(browser)["csrf_token"])
    token = login(other, old_token)
    assert session(browser)["user"]["id"] == other.pk
    assert (
        auth_post(
            browser, "login", {}, token, HTTP_X_EXPENSE_PILOT_USER="anonymous"
        ).json()["code"]
        == "session_changed"
    )
    assert (
        browser.get(
            reverse("api:expenses"), HTTP_X_EXPENSE_PILOT_USER=str(owner.pk)
        ).json()["code"]
        == "session_changed"
    )
    assert (
        auth_post(
            browser, "logout", {}, token, HTTP_X_EXPENSE_PILOT_USER=str(owner.pk)
        ).json()["code"]
        == "session_changed"
    )

    def upload(csrf, user):
        return browser.post(
            reverse("api:import-start"),
            {
                "file": SimpleUploadedFile(
                    "synthetic.csv",
                    b"Date;Category;Amount;Text;Note\n02-03-2024;;-2.50;Demo;\n",
                ),
                "import_format": "spiir_csv",
            },
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_X_EXPENSE_PILOT_USER=str(user.pk),
        )

    assert upload(old_token, other).json()["code"] == "csrf_failed"
    assert upload(token, owner).json()["code"] == "session_changed"
    assert browser.get(reverse("api:import-latest")).json()["result"] is None
    assert upload(token, other).json()["counts"]["total"] == 1
    expenses = reverse("api:expenses")
    assert [
        row["receiver"]
        for row in browser.get(expenses, {"month": "all"}).json()["rows"]
    ] == ["Demo"]
    login(owner, token)
    assert browser.get(expenses, {"month": "all"}).json()["rows"] == []


def test_legacy_auth_shares_session_and_reports_explicit_logout(browser, settings):
    settings.LEGACY_PAGES = True
    user = User.objects.create_user(username="legacy-wallet", password=PASSWORD)
    before = session(browser)
    response = browser.post(
        reverse("login"),
        {
            "username": user.username,
            "password": PASSWORD,
            "csrfmiddlewaretoken": before["csrf_token"],
        },
    )
    assert response.url == reverse("expense_list")
    current = session(browser)
    assert current["user"]["id"] == user.pk
    assert browser.get(reverse("logout")).status_code == 405
    assert browser.post(reverse("logout")).status_code == 403
    assert browser.post(
        reverse("logout"), {"csrfmiddlewaretoken": current["csrf_token"]}
    ).url == reverse("login")
    after = session(browser)
    assert after["user"] is None
    assert after["logout_marker"] and after["logout_marker"] != before["logout_marker"]


@pytest.mark.parametrize("page", ["login", "signup"])
def test_auth_routes_default_to_react_only_for_local_gets(browser, settings, page):
    settings.DEBUG = True
    settings.LEGACY_PAGES = settings.LOCAL_REACT_DEV = False
    url = reverse(page)
    assert "app-config" not in browser.get(url).text
    settings.LOCAL_REACT_DEV = True
    response = browser.get(url)
    assert "app-config" in response.text
    assert "no-store" in response.headers["Cache-Control"]
    assert "app-config" not in browser.get(reverse("admin:login")).text
    assert browser.post(url).status_code == 403
    settings.LEGACY_PAGES = True
    assert "app-config" not in browser.get(url).text
    settings.LEGACY_PAGES = settings.DEBUG = False
    assert "app-config" not in browser.get(url).text
