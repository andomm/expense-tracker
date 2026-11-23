import pytest
from django.test import Client
from django.urls import reverse


@pytest.fixture
def csrf_client(db):
    def make(user=None):
        client = Client(enforce_csrf_checks=True)
        if user is not None:
            client.force_login(user)
        client.defaults["HTTP_X_CSRFTOKEN"] = client.get(reverse("api:session")).json()[
            "csrf_token"
        ]
        return client

    return make


@pytest.fixture
def writer(owner, csrf_client):
    return csrf_client(owner)
