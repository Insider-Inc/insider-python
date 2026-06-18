"""
Django integration tests (legacy file — uses DjangoIntegration like wsgi.py).
"""

import pytest

from insider.client import Client, _set_active
from insider.dsn import DSN
from insider.integrations.django import DjangoIntegration

VALID = "https://t@insider.test/123e4567-e89b-12d3-a456-426614174000"


@pytest.fixture(autouse=True)
def _django_integration(settings, fake_client):
    settings.INSTALLED_APPS = [
        "django.contrib.contenttypes",
        "django.contrib.auth",
    ]
    settings.MIDDLEWARE = []
    settings.ROOT_URLCONF = "tests.django_urls"
    DjangoIntegration().setup_once()
    yield


@pytest.fixture
def fake_client(fake_transport):
    c = Client(
        DSN.parse(VALID),
        environment="test",
        release="0.0.0-test",
        transport=fake_transport,  # type: ignore[arg-type]
    )
    _set_active(c)
    yield c
    _set_active(None)


@pytest.fixture(autouse=True)
def _no_raise_on_500(client):
    client.raise_request_exception = False


@pytest.mark.django_db
def test_request_context_attached_on_500(client, fake_transport):
    response = client.get("/boom/?foo=bar", HTTP_USER_AGENT="pytest-ua")
    assert response.status_code == 500
    assert len(fake_transport.envelopes) == 1
    fp = fake_transport.envelopes[0]
    assert fp["exception_name"] == "ValueError"
    assert fp["request_method"] == "get"
    assert fp["request_path"] == "/boom/"
    assert fp["user_agent"] == "pytest-ua"


@pytest.mark.django_db
def test_pii_off_by_default(client, fake_transport):
    response = client.post("/boom/", data="secretbody", content_type="text/plain")
    assert response.status_code == 500
    fp = fake_transport.envelopes[0]
    assert fp.get("request_body") is None


@pytest.mark.django_db
def test_pii_on_includes_body(client, fake_client, fake_transport):
    fake_client.send_default_pii = True
    response = client.post("/boom/", data="hello", content_type="text/plain")
    assert response.status_code == 500
    fp = fake_transport.envelopes[0]
    assert fp["request_body"] == "hello"


@pytest.mark.django_db
def test_clean_request_emits_footprint(client, fake_transport):
    response = client.get("/ok/")
    assert response.status_code == 200
    assert len(fake_transport.envelopes) == 1
    assert fake_transport.envelopes[0]["request_path"] == "/ok/"


@pytest.mark.django_db
def test_disabled_mode_is_noop(client, fake_transport):
    _set_active(None)
    response = client.get("/boom/")
    assert response.status_code == 500
    assert fake_transport.envelopes == []


@pytest.mark.django_db
def test_scope_cleared_between_requests(client, fake_transport):
    client.get("/ok/")
    assert len(fake_transport.envelopes) == 1
    assert fake_transport.envelopes[0]["request_path"] == "/ok/"
