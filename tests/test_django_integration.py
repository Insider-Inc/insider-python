"""
Tests for DjangoIntegration — one footprint per HTTP cycle.
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

    fp = fake_transport.envelopes[0]
    assert fp["status_code"] == 500
    assert fp["request_method"] == "get"
    assert fp["request_path"] == "/boom/"
    assert fp["request_id"] is not None
    assert fp["exception_name"] is not None
    assert fp["stack_trace"]["value"] == "intentional explosion"


@pytest.mark.django_db
def test_integration_captures_response_body_when_pii_enabled(
    sdk_client, client, fake_transport
):
    sdk_client.send_default_pii = True
    response = client.get("/ok/")
    assert response.status_code == 200
    assert len(fake_transport.envelopes) == 1
    assert fake_transport.envelopes[0].get("response_body") == "ok"


@pytest.mark.django_db
def test_integration_clean_request_emits_one_footprint(client, fake_transport):
    response = client.get("/ok/")
    assert response.status_code == 200
    assert len(fake_transport.envelopes) == 1
    fp = fake_transport.envelopes[0]
    assert fp["status_code"] == 200
    assert fp["response_time"] >= 0
    assert fp["request_id"] is not None
    assert fp.get("exception_name") is None


@pytest.mark.django_db
def test_integration_auto_capture_can_be_disabled(client, fake_transport):
    from insider.integrations.django import handler as handler_module

    handler_module._auto_perf = False
    try:
        response = client.get("/ok/")
        assert response.status_code == 200
        assert fake_transport.envelopes == []
    finally:
        handler_module._auto_perf = True


@pytest.mark.django_db
def test_integration_disabled_mode_is_noop(client, fake_transport):
    _set_active(None)
    response = client.get("/boom/")
    assert response.status_code == 500
    assert fake_transport.envelopes == []


@pytest.mark.django_db
def test_integration_skips_default_ignore_paths(client, fake_transport):
    response = client.get("/static/app.js")
    assert response.status_code == 404
    assert fake_transport.envelopes == []


@pytest.mark.django_db
def test_ignored_path_exception_does_not_leak_to_next_request(
    sdk_client, client, fake_transport
):
    sdk_client.add_ignore_paths(["/health/"])
    response = client.get("/health/boom/")
    assert response.status_code == 500
    assert fake_transport.envelopes == []

    response = client.get("/ok/")
    assert response.status_code == 200
    assert len(fake_transport.envelopes) == 1
    assert fake_transport.envelopes[0].get("exception_name") is None
