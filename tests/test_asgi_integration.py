"""
Tests for Django ASGI support — handler patch, wrapper, and deduplication.
"""

from __future__ import annotations

import asyncio

import pytest
from django.core.asgi import get_asgi_application
from django.test import AsyncClient, Client

from insider.client import _set_active
from insider.integrations.django import DjangoIntegration, get_integration_status
from insider.integrations.django.asgi import wrap_asgi_application
from insider.integrations.django import handler as handler_module
from insider.integrations.django.request import build_request_ctx_from_scope
from tests.asgi_helpers import run_asgi


@pytest.fixture(autouse=True)
def _integration_env(settings, sdk_client):
    settings.INSTALLED_APPS = [
        "django.contrib.contenttypes",
        "django.contrib.auth",
    ]
    settings.MIDDLEWARE = []
    settings.ROOT_URLCONF = "tests.django_integration_urls"
    DjangoIntegration.reset_for_tests()
    DjangoIntegration().setup_once()
    yield
    _set_active(None)
    DjangoIntegration.reset_for_tests()
    handler_module._auto_perf = True


@pytest.fixture(autouse=True)
def _no_raise_on_500(client):
    client.raise_request_exception = False


def test_integration_status_reports_asgi_patch():
    status = get_integration_status()
    assert status["handler"] is True
    assert status["wsgi"] is True
    assert status["asgi_handler"] is True
    assert status["signals"] is True
    assert status["response_for_exception"] is True


def test_wsgi_client_still_one_footprint_per_request(client, fake_transport):
    response = client.get("/ok/")
    assert response.status_code == 200
    assert len(fake_transport.envelopes) == 1


def test_build_request_ctx_from_scope():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/items/",
        "query_string": b"q=1",
        "headers": [(b"user-agent", b"pytest-asgi")],
        "client": ("127.0.0.1", 12345),
    }
    ctx = build_request_ctx_from_scope(scope, send_default_pii=False)
    assert ctx["method"] == "GET"
    assert ctx["path"] == "/items/"
    assert ctx["query_string"] == "q=1"
    assert ctx["headers"]["user-agent"] == "pytest-asgi"
    assert ctx["ip"] == "127.0.0.1"


@pytest.mark.django_db
def test_asgi_async_client_handler_patch(fake_transport):
    async def _run() -> None:
        ac = AsyncClient()
        response = await ac.get("/ok/")
        assert response.status_code == 200

    asyncio.run(_run())
    assert len(fake_transport.envelopes) == 1
    assert fake_transport.envelopes[0]["request_path"] == "/ok/"


@pytest.mark.django_db
def test_wrap_asgi_application_one_footprint(fake_transport):
    DjangoIntegration.reset_for_tests()
    DjangoIntegration(auto_perf=False).setup_once()

    app = wrap_asgi_application(get_asgi_application())
    status, _ = run_asgi(app, "/ok/")
    assert status == 200
    assert len(fake_transport.envelopes) == 1
    fp = fake_transport.envelopes[0]
    assert fp["status_code"] == 200
    assert fp["request_path"] == "/ok/"


@pytest.mark.django_db
def test_asgi_async_client_captures_exception(fake_transport):
    async def _run() -> None:
        ac = AsyncClient(raise_request_exception=False)
        response = await ac.get("/boom/")
        assert response.status_code == 500

    asyncio.run(_run())
    assert len(fake_transport.envelopes) == 1
    assert fake_transport.envelopes[0].get("exception_name") is not None


@pytest.mark.django_db
def test_wrap_captures_exception(fake_transport):
    DjangoIntegration.reset_for_tests()
    DjangoIntegration(auto_perf=False).setup_once()
    app = wrap_asgi_application(get_asgi_application())

    status, _ = run_asgi(app, "/boom/")
    assert status == 500
    assert len(fake_transport.envelopes) == 1
    assert fake_transport.envelopes[0].get("exception_name") is not None


@pytest.mark.django_db
def test_wrap_with_auto_perf_disabled_emits_once(fake_transport):
    """Handler patch present but auto_perf off — only wrapper beams."""
    DjangoIntegration.reset_for_tests()
    DjangoIntegration(auto_perf=False).setup_once()
    assert get_integration_status()["handler_auto_perf"] is False

    app = wrap_asgi_application(get_asgi_application())
    run_asgi(app, "/ok/")
    run_asgi(app, "/boom/")

    paths = [e["request_path"] for e in fake_transport.envelopes]
    assert paths.count("/ok/") == 1
    assert paths.count("/boom/") == 1
    assert len(fake_transport.envelopes) == 2
