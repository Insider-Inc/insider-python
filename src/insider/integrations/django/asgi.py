"""
ASGI support for Django — escape capture and optional HTTP wrapper.

`install()` patches `ASGIHandler` (mirrors `wsgi.install()`).

`wrap_asgi_application()` wraps the HTTP branch of a Channels
`ProtocolTypeRouter` (or plain `get_asgi_application()`). Use with
`DjangoIntegration(auto_perf=False)` so footprints are not emitted twice.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, MutableMapping, Optional

from ... import capture_exception
from ...client import _client
from ...safety import debug, safe
from ...stacktrace import exception_payload
from .perf import emit_http_footprint
from .request import build_request_ctx_from_scope

ASGIApp = Callable[..., Any]

_handler_patched = False


def install() -> None:
    """Patch ASGIHandler to capture exceptions that escape Django entirely."""
    global _handler_patched
    if _handler_patched:
        return
    try:
        from django.core.handlers.asgi import ASGIHandler
    except ImportError:
        debug("django ASGIHandler unavailable; skipping ASGI patch")
        return

    old_call = ASGIHandler.__call__

    @safe
    async def patched_call(
        self: Any,
        scope: MutableMapping[str, Any],
        receive: Callable[..., Any],
        send: Callable[..., Any],
    ) -> Any:
        if _client() is None:
            return await old_call(self, scope, receive, send)
        try:
            return await old_call(self, scope, receive, send)
        except BaseException as exc:
            capture_exception(exc)
            raise

    ASGIHandler.__call__ = patched_call  # type: ignore[method-assign]
    _handler_patched = True


def wrap_asgi_application(application: ASGIApp) -> ASGIApp:
    """
    Wrap a Django (or other) ASGI HTTP app to emit one footprint per request.

    Pass the return value of `get_asgi_application()` or the ``"http"`` branch
    of a ``ProtocolTypeRouter``. Pair with ``DjangoIntegration(auto_perf=False)``.
    """
    return _InsiderAsgiHttpWrapper(application)


class _InsiderAsgiHttpWrapper:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Callable[..., Any],
        send: Callable[..., Any],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        client = _client()
        if client is None:
            await self.app(scope, receive, send)
            return

        trace_id = uuid.uuid4().hex
        client.scope.set_trace_id(trace_id)
        client.scope.set_request(
            build_request_ctx_from_scope(scope, client.send_default_pii)
        )

        start = time.perf_counter()
        status_code: Optional[int] = None

        async def send_wrapper(message: Dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except BaseException as exc:
            block = exception_payload(
                exc, in_app_include=client.scope.static.in_app_include
            )
            client.scope.set_pending_exception(block)
            raise
        finally:
            path = str(scope.get("path") or "/")
            method = str(scope.get("method") or "GET")
            emit_http_footprint(
                path=path,
                method=method,
                duration_ms=(time.perf_counter() - start) * 1000.0,
                status_code=status_code,
                trace_id=trace_id,
            )
            client.scope.clear_request_cycle()
