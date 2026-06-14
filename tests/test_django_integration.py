"""
DjangoIntegration tests — Sentry-style hooks without middleware.
"""

from __future__ import annotations

import pytest

from insider.client import _set_active
from insider.integrations.django import DjangoIntegration


@pytest.fixture(autouse=True)
def _integration_env(settings, sdk_client):
    settings.INSTALLED_APPS = [
        "django.contrib.contenttypes",
        "django.contrib.auth",
    ]
    settings.MIDDLEWARE = []
    settings.ROOT_URLCONF = "tests.django_integration_urls"
    DjangoIntegration().setup_once()
    yield
    _set_active(None)


@pytest.fixture(autouse=True)
def _no_raise_on_500(client):
    client.raise_request_exception = False


@pytest.mark.django_db
def test_integration_captures_view_exception(client, fake_transport):
    response = client.get("/boom/?foo=bar", HTTP_USER_AGENT="pytest-ua")
    assert response.status_code == 500
    assert len(fake_transport.envelopes) == 1
    env = fake_transport.envelopes[0]
    assert env["kind"] == "error"
    assert env["message"] == "intentional explosion"
    request_ctx = env["payload"]["request"]
    assert request_ctx["method"] == "GET"
    assert request_ctx["path"] == "/boom/"
    assert request_ctx["query_string"] == "foo=bar"
    assert request_ctx["headers"]["user-agent"] == "pytest-ua"


@pytest.mark.django_db
def test_integration_clean_request_does_not_capture(client, fake_transport):
    response = client.get("/ok/")
    assert response.status_code == 200
    assert fake_transport.envelopes == []


@pytest.mark.django_db
def test_integration_disabled_mode_is_noop(client, fake_transport):
    _set_active(None)
    response = client.get("/boom/")
    assert response.status_code == 500
    assert fake_transport.envelopes == []
