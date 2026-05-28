"""
Django integration tests.

We install a `Client` with the in-memory FakeTransport so the middleware
captures exceptions without doing any network I/O. Then we run requests
through Django's test client and assert that the right beacons were
recorded.
"""

import pytest

import insider
from insider.client import Client, _set_active
from insider.dsn import DSN

VALID = "https://t@insider.test/123e4567-e89b-12d3-a456-426614174000"


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
    """Let the test client return 500 instead of re-raising the view's exception.

    Production Django renders a 500 response when middleware doesn't handle
    the exception. Django's test client re-raises by default, which would
    short-circuit our middleware's `process_exception` from being meaningful
    in tests. Switching this off makes the test behave like production.
    """
    client.raise_request_exception = False


@pytest.mark.django_db
def test_request_context_attached_on_500(client, fake_client, fake_transport):
    """A 500-ing view triggers `process_exception` → capture with request ctx."""
    response = client.get("/boom/?foo=bar", HTTP_USER_AGENT="pytest-ua")
    assert response.status_code == 500
    assert len(fake_transport.envelopes) == 1
    env = fake_transport.envelopes[0]
    assert env["kind"] == "error"
    assert env["message"] == "intentional explosion"
    assert env["payload"]["exception"]["type"] == "ValueError"
    request_ctx = env["payload"]["request"]
    assert request_ctx["method"] == "GET"
    assert request_ctx["path"] == "/boom/"
    assert request_ctx["query_string"] == "foo=bar"
    assert request_ctx["headers"]["user-agent"] == "pytest-ua"


@pytest.mark.django_db
def test_pii_off_by_default(client, fake_client, fake_transport):
    response = client.post("/boom/", data="secretbody", content_type="text/plain")
    assert response.status_code == 500
    request_ctx = fake_transport.envelopes[0]["payload"]["request"]
    assert "body" not in request_ctx
    assert "user" not in request_ctx


@pytest.mark.django_db
def test_pii_on_includes_body(client, fake_client, fake_transport):
    fake_client.send_default_pii = True
    response = client.post("/boom/", data="hello", content_type="text/plain")
    assert response.status_code == 500
    request_ctx = fake_transport.envelopes[0]["payload"]["request"]
    assert request_ctx["body"] == "hello"


@pytest.mark.django_db
def test_clean_request_does_not_capture(client, fake_client, fake_transport):
    response = client.get("/ok/")
    assert response.status_code == 200
    assert fake_transport.envelopes == []


@pytest.mark.django_db
def test_disabled_mode_middleware_is_noop(client, fake_transport):
    """No active client → middleware adds nothing, doesn't capture."""
    _set_active(None)
    response = client.get("/boom/")
    assert response.status_code == 500
    assert fake_transport.envelopes == []


@pytest.mark.django_db
def test_scope_cleared_between_requests(client, fake_client, fake_transport):
    client.get("/ok/")
    # After a clean request, no request context should leak into a manual capture
    insider.capture_message("after-request")
    env = fake_transport.envelopes[0]
    assert "request" not in env["payload"]
