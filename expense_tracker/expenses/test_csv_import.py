from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from .models import Category, Expense

START = "/api/imports/"
LATEST = "/api/imports/latest-result/"
OP = "osuuspankki_csv"
SPIIR = "spiir_csv"
OP_HEADER = "Arvopäivä;Selitys;Määrä EUROA;Saaja/Maksaja;Viesti\n"
SPIIR_HEADER = "Date;Category;Amount;Text;Note\n"
OP_ROW = "2024-03-02;Original;-12,35;North Market;train\n"


@pytest.fixture
def accounts(db):
    owner, other = (
        User.objects.create_user(name) for name in ("csv-owner", "csv-other")
    )
    Category.objects.filter(user__in=(owner, other)).delete()
    client, other_client = (Client(enforce_csrf_checks=True) for _ in range(2))
    client.force_login(owner)
    other_client.force_login(other)
    return owner, other, client, other_client


def csrf(client):
    return client.get(reverse("api:session")).json()["csrf_token"]


def upload(client, data, *, format=OP, url=START, **headers):
    if isinstance(data, str):
        data = data.encode()
    return client.post(
        url,
        {"import_format": format, "file": SimpleUploadedFile("export.csv", data)},
        **headers,
    )


@pytest.mark.parametrize(
    ("format", "data", "date", "description", "amount"),
    [
        (OP, "\ufeff" + OP_HEADER + OP_ROW, "2024-03-02", "train", "-12.35"),
        (
            SPIIR,
            SPIIR_HEADER
            + '"02-03-2024";Original;"12.35";North Market;"train; refund"\n',
            "2024-03-02",
            "train; refund",
            "12.35",
        ),
    ],
    ids=["op-decimal-comma-and-bom", "spiir-quoted-and-signed"],
)
def test_import_formats_preserve_values_and_keyword_priority(
    accounts, format, data, date, description, amount
):
    owner, other, client, _ = accounts
    food = Category.objects.create(user=owner, name="Food", keywords="market")
    market = Category.objects.create(
        user=owner, name="Market", parent=food, keywords="north market"
    )
    Category.objects.create(user=owner, name="Travel", keywords="train,original")
    Category.objects.create(user=other, name="Unrelated", keywords="north market")

    response = upload(client, data, format=format, HTTP_X_CSRFTOKEN=csrf(client))

    assert response.status_code == 200, response.content
    outcome = response.json()
    assert outcome["result_url"] == reverse("import_summary")
    assert outcome["counts"] == {"total": 1, "categorized": 1, "uncategorized": 0}
    row = Expense.objects.get()
    assert row.user == owner
    assert row.date.isoformat() == date
    assert row.receiver == "North Market" and row.description == description
    assert row.category == "Original" and row.category_obj == market
    assert row.amount == row.user_share == Decimal(amount)
    result = client.get(LATEST).json()["result"]
    assert result["id"] == outcome["result_id"]
    assert result["counts"] == outcome["counts"]
    assert result["uncategorized_preview"] == {"rows": [], "omitted": 0}


@pytest.mark.parametrize(
    ("format", "data", "row", "message"),
    [
        (OP, OP_HEADER + OP_ROW + "2024-02-30;;1;;private memo\n", 3, "valid date"),
        (
            SPIIR,
            SPIIR_HEADER + "02-03-2024;;1;;\n2024-03-03;;2;;private memo\n",
            3,
            "valid date",
        ),
        (OP, OP_HEADER + OP_ROW + "2024-03-02;;NaN;;private memo\n", 3, "valid amount"),
        (
            OP,
            OP_HEADER + OP_ROW + "2024-03-02;;Infinity;;private memo\n",
            3,
            "valid amount",
        ),
        (OP, OP_HEADER + OP_ROW + "2024-03-02;;;;private memo\n", 3, "valid amount"),
        (
            OP,
            OP_HEADER + OP_ROW + "2024-03-02;;100000000;;private memo\n",
            3,
            "eight whole digits",
        ),
        (
            OP,
            OP_HEADER + OP_ROW + "2024-03-02;;1,001;;private memo\n",
            3,
            "two decimal places",
        ),
        (
            OP,
            OP_HEADER + OP_ROW + f"2024-03-02;;1;{'X' * 101};private memo\n",
            3,
            "receiver must be",
        ),
        (
            OP,
            OP_HEADER + OP_ROW + f"2024-03-02;{'X' * 101};1;;private memo\n",
            3,
            "category must be",
        ),
        (
            OP,
            OP_HEADER + OP_ROW + "2024-03-02;;1;;private memo\0\n",
            3,
            "null characters",
        ),
        (
            OP,
            OP_HEADER + OP_ROW + "2024-03-02;;1;private memo\n",
            3,
            "number of columns",
        ),
        (
            OP,
            OP_HEADER + OP_ROW + "2024-03-02;;1;private memo;;\n",
            3,
            "number of columns",
        ),
        (
            OP,
            OP_HEADER
            + '2024-03-02;;1;;"first\nsecond"\n\n2024-03-02;;1;;"private memo',
            5,
            "CSV quoting",
        ),
        (OP, SPIIR_HEADER + "02-03-2024;;1;;private memo\n", 1, "selected file format"),
        (OP, OP_HEADER + "\n", None, "no transactions"),
        (OP, OP_HEADER.encode() + b"\xff private memo\n", None, "UTF-8 encoding"),
    ],
    ids=[
        "op-invalid-date",
        "spiir-invalid-date",
        "nan",
        "infinity",
        "empty-amount",
        "amount-overflow",
        "sub-cent",
        "receiver-length",
        "category-length",
        "null",
        "missing-cell",
        "extra-cell",
        "malformed-quote-after-multiline",
        "wrong-format",
        "headers-only",
        "invalid-encoding",
    ],
)
def test_invalid_import_leaves_all_expenses_and_latest_success_unchanged(
    accounts, format, data, row, message
):
    owner, _, client, _ = accounts
    headers = {"HTTP_X_CSRFTOKEN": csrf(client)}
    first_id = upload(client, OP_HEADER + OP_ROW, **headers).json()["result_id"]
    previous_expense = Expense.objects.get(user=owner)
    previous = client.get(LATEST).json()["result"]
    assert previous["id"] == first_id

    response = upload(client, data, format=format, **headers)

    assert response.status_code == 422
    assert response.json().get("row") == row
    error = response.json()["fields"]["file"][0]
    if row is not None:
        assert error.startswith(f"Row {row}:")
    assert message in error
    assert (
        b"private memo" not in response.content
        and b"North Market" not in response.content
    )
    assert list(Expense.objects.all()) == [previous_expense]
    assert client.get(LATEST).json()["result"] == previous


def test_bounded_preview_and_read_only_latest_result_are_scoped_to_the_session(
    accounts,
):
    owner, other, client, other_client = accounts
    Category.objects.create(
        user=other, name="Other owner's match", keywords="unmatched"
    )
    foreign = Expense.objects.create(
        user=other, date="2024-03-02", receiver="Foreign", amount="-1.00"
    )
    another_session = Client(enforce_csrf_checks=True)
    another_session.force_login(owner)
    assert client.get(LATEST).json() == {"result": None}
    lines = "".join(f"2024-03-02;;-4,50;Unmatched {i};{'Z' * 250}\n" for i in range(52))
    headers = {"HTTP_X_CSRFTOKEN": csrf(client)}
    first = upload(client, OP_HEADER + lines, **headers).json()
    assert first["counts"] == {"total": 52, "categorized": 0, "uncategorized": 52}
    initial = client.get(LATEST)
    repeat = client.get(LATEST)
    assert (
        "no-store" in initial.headers["Cache-Control"]
        and "Cookie" in initial.headers["Vary"]
    )
    assert initial.json() == repeat.json()
    result = initial.json()["result"]
    preview = result["uncategorized_preview"]
    assert result["id"] == first["result_id"]
    assert preview["omitted"] == 2
    stored = list(Expense.objects.filter(user=owner).order_by("id"))
    assert len(stored) == 52
    assert [row["id"] for row in preview["rows"]] == [row.pk for row in stored[:50]]
    example = preview["rows"][0]
    assert example == {
        "id": stored[0].pk,
        "date": "2024-03-02",
        "description": "Z" * 199 + "…",
        "receiver": "Unmatched 0",
        "amount": "-4.50",
        "edit_url": reverse("expense_edit", args=[stored[0].pk]),
    }
    assert len(stored[0].description) == 250
    assert client.get(example["edit_url"]).status_code == 200
    assert other_client.get(example["edit_url"]).status_code == 404
    assert client.get(reverse("expense_edit", args=[foreign.pk])).status_code == 404
    assert (
        another_session.get(LATEST).json()
        == other_client.get(LATEST).json()
        == {"result": None}
    )
    stored[0].delete()
    assert (
        client.get(LATEST).json()["result"]["uncategorized_preview"]["rows"][0][
            "edit_url"
        ]
        is None
    )
    second = upload(client, OP_HEADER + OP_ROW, **headers).json()
    assert second["result_id"] != first["result_id"]
    assert client.get(LATEST).json()["result"]["id"] == second["result_id"]
    client.logout()
    assert client.get(LATEST).status_code == 401
    client.force_login(owner)
    assert client.get(LATEST).json() == {"result": None}


def test_multipart_rejects_unverified_and_unauthorized_requests(accounts):
    _, other, client, _ = accounts
    headers = {"HTTP_X_CSRFTOKEN": csrf(client)}
    path = OP_HEADER + OP_ROW
    no_token = upload(client, path)
    assert (no_token.status_code, no_token.json()["code"]) == (403, "csrf_failed")
    wrong_type = client.post(START, {}, content_type="application/json", **headers)
    assert (wrong_type.status_code, wrong_type.json()["code"]) == (
        400,
        "invalid_request",
    )
    assert (
        client.get(START).status_code
        == client.post(LATEST, {}, **headers).status_code
        == 405
    )
    wrong_user = upload(
        client, path, HTTP_X_EXPENSE_PILOT_USER=str(other.pk), **headers
    )
    assert (wrong_user.status_code, wrong_user.json()["code"]) == (
        401,
        "session_changed",
    )
    wrong_format = upload(client, path, format="private invalid value", **headers)
    assert wrong_format.status_code == 422
    assert wrong_format.json()["fields"]["import_format"] == ["Choose OP or Spiir."]
    assert client.get(LATEST).json() == {"result": None}
    client.session.delete()
    assert (
        upload(client, path, **headers).status_code
        == client.get(LATEST).status_code
        == 401
    )
    assert not Expense.objects.exists()


def test_legacy_upload_uses_the_same_atomic_import_and_repeatable_result(
    accounts, settings
):
    owner, _, client, _ = accounts
    settings.DEBUG = settings.LOCAL_REACT_DEV = settings.LEGACY_PAGES = True
    start, result = reverse("upload_csv"), reverse("import_summary")
    assert "No import result in this session" in client.get(result).content.decode()
    path = OP_HEADER + OP_ROW
    assert upload(client, path, url=start).status_code == 403

    def submit(data):
        return client.post(
            start,
            {
                "import_format": OP,
                "file": SimpleUploadedFile("export.csv", data.encode()),
                "csrfmiddlewaretoken": csrf(client),
            },
        )

    bad = submit(path + "2024-02-30;;1;;private memo\n")
    assert bad.status_code == 422 and "Row 3:" in bad.content.decode()
    assert not Expense.objects.exists()
    assert submit(path).url == result
    edit = reverse("expense_edit", args=[Expense.objects.get(user=owner).pk])
    for _ in range(2):
        page = client.get(result)
        assert page.templates[0].name == "expenses/import_summary.html"
        assert edit in page.content.decode()
        assert "no-store" in page.headers["Cache-Control"]
    assert Expense.objects.count() == 1
    assert client.get(LATEST).json()["result"]["counts"]["total"] == 1


@pytest.mark.parametrize(
    ("local", "debug", "legacy", "candidate", "react"),
    [
        (True, True, False, True, True),
        (True, True, False, False, False),
        (True, True, True, True, False),
        (False, True, False, True, False),
        (True, False, False, True, False),
    ],
    ids=["candidate", "default", "fallback", "plain-django", "debug-disabled"],
)
def test_upload_and_result_routes_move_together(
    accounts, settings, local, debug, legacy, candidate, react
):
    _, _, client, _ = accounts
    settings.LOCAL_REACT_DEV, settings.DEBUG, settings.LEGACY_PAGES = (
        local,
        debug,
        legacy,
    )
    settings.CSV_IMPORT_REACT_CANDIDATE = candidate
    start = reverse("upload_csv")
    for url, screen, fallback in (
        (start, "csv-upload", "expenses/upload_csv.html"),
        (
            reverse("import_summary"),
            "csv-import-result",
            "expenses/import_summary.html",
        ),
    ):
        response = client.get(url)
        assert response.templates[0].name == ("react_host.html" if react else fallback)
        if react:
            assert response.context["app"]["screen"] == screen
    if react:
        response = upload(
            client, OP_HEADER + OP_ROW, url=start, HTTP_X_CSRFTOKEN=csrf(client)
        )
        assert response.status_code == 405
        assert not Expense.objects.exists()
