"""
DRF tests for DjangoIntegration — one footprint per HTTP cycle.
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

    fp = fake_transport.envelopes[0]
    assert fp["status_code"] == 500
    assert fp["stack_trace"]["value"] == "drf intentional explosion"
    assert fp["request_method"] == "get"
    assert fp["request_path"] == "/api/boom/"
    assert fp["user_agent"] == "pytest-drf"


@pytest.mark.django_db
def test_drf_handled_api_exception_emits_footprint(client, fake_transport):
    response = client.get("/api/bad-request/")
    assert response.status_code == 400
    assert len(fake_transport.envelopes) == 1
    fp = fake_transport.envelopes[0]
    assert fp["status_code"] == 400
    assert fp.get("exception_name") is None


@pytest.mark.django_db
def test_drf_clean_request_emits_footprint(client, fake_transport):
    response = client.get("/api/ok/")
    assert response.status_code == 200
    assert len(fake_transport.envelopes) == 1
    assert fake_transport.envelopes[0]["request_path"] == "/api/ok/"
