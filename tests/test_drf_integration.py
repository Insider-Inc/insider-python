"""
DRF tests for DjangoIntegration — no middleware, no EXCEPTION_HANDLER wiring.
"""

from __future__ import annotations

import pytest

from insider.client import _set_active
from insider.integrations.django import DjangoIntegration

drf = pytest.importorskip("rest_framework")


@pytest.fixture(autouse=True)
def _drf_integration_env(settings, sdk_client):
    settings.INSTALLED_APPS = [
        "django.contrib.contenttypes",
        "django.contrib.auth",
        "rest_framework",
    ]
    settings.MIDDLEWARE = []
    settings.ROOT_URLCONF = "tests.django_drf_urls"
    DjangoIntegration().setup_once()
    yield
    _set_active(None)


@pytest.fixture(autouse=True)
def _no_raise_on_500(client):
    client.raise_request_exception = False


@pytest.mark.django_db
def test_drf_unhandled_exception_is_captured(client, fake_transport):
    response = client.get("/api/boom/", HTTP_USER_AGENT="pytest-drf")
    assert response.status_code == 500
    assert len(fake_transport.envelopes) == 1
    env = fake_transport.envelopes[0]
    assert env["kind"] == "error"
    assert env["message"] == "drf intentional explosion"
    request_ctx = env["payload"]["request"]
    assert request_ctx["method"] == "GET"
    assert request_ctx["path"] == "/api/boom/"
    assert request_ctx["headers"]["user-agent"] == "pytest-drf"


@pytest.mark.django_db
def test_drf_handled_api_exception_is_not_captured(client, fake_transport):
    response = client.get("/api/bad-request/")
    assert response.status_code == 400
    assert fake_transport.envelopes == []


@pytest.mark.django_db
def test_drf_clean_request_does_not_capture(client, fake_transport):
    response = client.get("/api/ok/")
    assert response.status_code == 200
    assert fake_transport.envelopes == []
