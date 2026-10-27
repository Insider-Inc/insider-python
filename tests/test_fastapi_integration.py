"""
Tests for FastAPIIntegration — one flat footprint per HTTP cycle.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
import pytest
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import PlainTextResponse

from insider.client import _set_active
from insider.integrations.fastapi import FastAPIIntegration
from insider.integrations.fastapi import asgi as asgi_module
from insider.integrations.logging import LoggingIntegration


@pytest.fixture(autouse=True)
def _install(sdk_client):
    FastAPIIntegration.reset_for_tests()
    FastAPIIntegration().setup_once()
    yield
    asgi_module._auto_perf = True
    _set_active(None)


def _request(app: FastAPI, method: str, path: str, **kwargs):
    async def _run():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(_run())


def test_clean_request_emits_one_footprint(fake_transport):
    app = FastAPI(redirect_slashes=False)

    @app.get("/ok")
    def ok() -> PlainTextResponse:
        return PlainTextResponse("ok")

    response = _request(app, "GET", "/ok", headers={"user-agent": "pytest-ua"})
    assert response.status_code == 200
    assert len(fake_transport.envelopes) == 1
    footprint = fake_transport.envelopes[0]
    assert footprint["status_code"] == 200
    assert footprint["request_method"] == "get"
    assert footprint["request_path"] == "/ok"
    assert footprint["request_id"]
    assert footprint["response_time"] >= 0
    assert footprint.get("exception_name") is None
    assert footprint["framework"] == "fastapi"
    assert footprint["language"] == "python"
    assert footprint["user_agent"] == "pytest-ua"
    assert footprint.get("request_body") is None
    assert footprint.get("response_body") is None


def test_unhandled_exception_is_on_the_same_footprint(fake_transport):
    app = FastAPI(redirect_slashes=False)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("intentional explosion")

    response = _request(app, "GET", "/boom")
    assert response.status_code == 500
    assert len(fake_transport.envelopes) == 1
    footprint = fake_transport.envelopes[0]
    assert footprint["status_code"] == 500
    assert footprint["exception_name"] == "RuntimeError"
    assert footprint["stack_trace"]["value"] == "intentional explosion"
    assert footprint["stack_trace"]["frames"][-1]["in_app"] is True


def test_http_exception_is_one_footprint_without_a_second_beacon(fake_transport):
    app = FastAPI(redirect_slashes=False)

    @app.get("/missing")
    def missing() -> None:
        raise HTTPException(status_code=404, detail="gone")

    response = _request(app, "GET", "/missing")
    assert response.status_code == 404
    assert len(fake_transport.envelopes) == 1
    assert fake_transport.envelopes[0]["status_code"] == 404
    assert fake_transport.envelopes[0].get("exception_name") is None


def test_validation_error_is_one_footprint(fake_transport):
    app = FastAPI(redirect_slashes=False)

    @app.get("/items/{item_id}")
    def item(item_id: int) -> dict:
        return {"item_id": item_id}

    response = _request(app, "GET", "/items/not-a-number")
    assert response.status_code == 422
    assert len(fake_transport.envelopes) == 1
    assert fake_transport.envelopes[0]["status_code"] == 422
    assert fake_transport.envelopes[0].get("exception_name") is None


def test_disabled_mode_is_noop(fake_transport):
    app = FastAPI(redirect_slashes=False)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("intentional explosion")

    _set_active(None)
    response = _request(app, "GET", "/boom")
    assert response.status_code == 500
    assert fake_transport.envelopes == []


def test_auto_capture_can_be_disabled(fake_transport):
    app = FastAPI(redirect_slashes=False)

    @app.get("/ok")
    def ok() -> PlainTextResponse:
        return PlainTextResponse("ok")

    asgi_module._auto_perf = False
    response = _request(app, "GET", "/ok")
    assert response.status_code == 200
    assert fake_transport.envelopes == []


def test_skips_builtin_ignore_paths(fake_transport):
    app = FastAPI(redirect_slashes=False)

    @app.get("/favicon.ico")
    def favicon() -> PlainTextResponse:
        return PlainTextResponse("ico")

    response = _request(app, "GET", "/favicon.ico")
    assert response.status_code == 200
    assert fake_transport.envelopes == []


def test_ignored_path_does_not_leak_into_next_request(sdk_client, fake_transport):
    app = FastAPI(redirect_slashes=False)

    @app.get("/health/boom")
    def health_boom() -> None:
        raise RuntimeError("health down")

    @app.get("/ok")
    def ok() -> PlainTextResponse:
        return PlainTextResponse("ok")

    sdk_client.add_ignore_paths(["/health/"])
    assert _request(app, "GET", "/health/boom").status_code == 500
    assert fake_transport.envelopes == []
    assert _request(app, "GET", "/ok").status_code == 200
    assert len(fake_transport.envelopes) == 1
    assert fake_transport.envelopes[0].get("exception_name") is None


def test_pii_captures_bodies_and_scrubs_keys(sdk_client, fake_transport):
    app = FastAPI(redirect_slashes=False)

    @app.post("/echo")
    async def echo(payload: dict) -> dict:
        return payload

    sdk_client.send_default_pii = True
    sdk_client.scrub_defaults = True
    response = _request(app, "POST", "/echo", json={"password": "secret", "name": "ada"})
    assert response.status_code == 200
    assert len(fake_transport.envelopes) == 1
    footprint = fake_transport.envelopes[0]
    assert footprint["request_body"]["password"] == "[Filtered]"
    assert footprint["request_body"]["name"] == "ada"
    assert footprint["response_body"]["password"] == "[Filtered]"


def test_user_from_scope_when_pii_enabled(sdk_client, fake_transport):
    app = FastAPI(redirect_slashes=False)

    @app.middleware("http")
    async def attach_user(request, call_next):
        request.scope["user"] = type("User", (), {"id": 7, "is_authenticated": True})()
        return await call_next(request)

    @app.get("/ok")
    def ok() -> PlainTextResponse:
        return PlainTextResponse("ok")

    sdk_client.send_default_pii = True
    response = _request(app, "GET", "/ok")
    assert response.status_code == 200
    assert fake_transport.envelopes[0]["request_user"] == "7"


def test_anonymous_user_without_auth(sdk_client, fake_transport):
    app = FastAPI(redirect_slashes=False)

    @app.get("/ok")
    def ok() -> PlainTextResponse:
        return PlainTextResponse("ok")

    sdk_client.send_default_pii = True
    response = _request(app, "GET", "/ok")
    assert response.status_code == 200
    assert fake_transport.envelopes[0]["request_user"] == "anonymous"


def test_request_logs_fold_into_the_footprint(sdk_client, fake_transport):
    app = FastAPI(redirect_slashes=False)
    logger = logging.getLogger("fastapi.test.checkout")

    @app.get("/ok")
    async def ok() -> PlainTextResponse:
        logger.info("checkout completed")
        return PlainTextResponse("ok")

    sdk_client.enable_logs = True
    logger = logging.getLogger("fastapi.test.checkout")
    logger.setLevel(logging.INFO)
    LoggingIntegration().setup_once()
    response = _request(app, "GET", "/ok")
    assert response.status_code == 200
    assert len(fake_transport.envelopes) == 1
    messages = [line["message"] for line in fake_transport.envelopes[0]["system_logs"]]
    assert "checkout completed" in messages


def test_sdk_failure_does_not_break_the_response(sdk_client, monkeypatch):
    app = FastAPI(redirect_slashes=False)

    @app.get("/ok")
    def ok() -> PlainTextResponse:
        return PlainTextResponse("ok")

    def explode(*_args, **_kwargs):
        raise RuntimeError("sdk bug")

    monkeypatch.setattr(sdk_client, "capture_request", explode)
    response = _request(app, "GET", "/ok")
    assert response.status_code == 200


def test_websocket_is_not_a_footprint(fake_transport):
    app = FastAPI(redirect_slashes=False)

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_text("hi")
        await websocket.close()

    sent = []

    incoming = [
        {"type": "websocket.connect"},
        {"type": "websocket.disconnect"},
    ]

    async def receive():
        return incoming.pop(0)

    async def send(message):
        sent.append(message)

    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "path": "/ws",
        "raw_path": b"/ws",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 123),
        "scheme": "ws",
        "server": ("test", 80),
        "root_path": "",
        "subprotocols": [],
    }

    asyncio.run(app(scope, receive, send))
    assert any(message.get("text") == "hi" for message in sent)
    assert fake_transport.envelopes == []


def test_concurrent_requests_do_not_share_exceptions(fake_transport):
    app = FastAPI(redirect_slashes=False)

    @app.get("/ok")
    async def ok() -> dict:
        await asyncio.sleep(0.05)
        return {"ok": True}

    @app.get("/boom")
    async def boom() -> None:
        await asyncio.sleep(0.05)
        raise RuntimeError("intentional explosion")

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await asyncio.gather(
                client.get("/ok"),
                client.get("/boom"),
                return_exceptions=True,
            )

    asyncio.run(run())
    assert len(fake_transport.envelopes) == 2
    by_path = {item["request_path"]: item for item in fake_transport.envelopes}
    assert by_path["/ok"]["status_code"] == 200
    assert by_path["/ok"].get("exception_name") is None
    assert by_path["/boom"]["status_code"] == 500
    assert by_path["/boom"]["exception_name"] == "RuntimeError"
