"""
Patch `BaseHandler.get_response` / `get_response_async` for request context
and auto perf timing.

We patch the handler (not middleware) because:

  - Customers already init in `wsgi.py` / `asgi.py` without touching INSTALLED_APPS.
  - The patch wraps the entire handler, including middleware inside Django's
    request cycle.
  - Perf timing in `finally` runs once per request whether the view returns
    200 or raises (converted to 500 by Django).

Django 4.1+ ASGI uses `get_response_async` for the async request path
(Daphne, `AsyncClient`). Both sync and async entrypoints are patched.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable

from ...client import _client
from ...safety import debug, safe
from .perf import emit_request_envelope
from .capture import sync_pending_from_request
from .request import read_response_body

_patched = False
_auto_perf = True


def _finalize_request_cycle(
    request: Any,
    *,
    start: float,
    response: Any,
    status_code: int | None,
    trace_id: str,
) -> None:
    client = _client()
    if client is None:
        return
    duration_ms = (time.perf_counter() - start) * 1000.0
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    sync_pending_from_request(request)
    if _auto_perf:
        if client.send_default_pii and response is not None:
            body = read_response_body(response)
            if body is not None:
                ctx = dict(client.scope.current_request() or {})
                ctx["response_body"] = body
                client.scope.set_request(ctx)
        emit_request_envelope(
            request,
            duration_ms=duration_ms,
            status_code=status_code,
            trace_id=trace_id,
        )
        client.scope.clear_request_cycle()
    # When auto_perf=False (e.g. wrap_asgi_application), leave scope intact
    # for the outer ASGI wrapper to emit one combined footprint.


def install(*, auto_perf: bool = True) -> None:
    global _patched, _auto_perf
    _auto_perf = auto_perf
    if _patched:
        return
    try:
        from django.core.handlers.base import BaseHandler
    except ImportError:
        debug("django BaseHandler unavailable; skipping get_response patch")
        return

    old_get_response = BaseHandler.get_response
    old_get_response_async = BaseHandler.get_response_async

    @safe
    def patched_get_response(self: Any, request: Any) -> Any:
        client = _client()
        if client is None:
            return old_get_response(self, request)

        trace_id = uuid.uuid4().hex
        client.scope.set_trace_id(trace_id)
        from .request import build_request_ctx

        ctx = build_request_ctx(request, client.send_default_pii)
        client.scope.set_request(ctx)

        start = time.perf_counter()
        response = None
        status_code: int | None = None
        try:
            response = old_get_response(self, request)
            status_code = getattr(response, "status_code", None)
            return response
        finally:
            _finalize_request_cycle(
                request,
                start=start,
                response=response,
                status_code=status_code,
                trace_id=trace_id,
            )

    @safe
    async def patched_get_response_async(self: Any, request: Any) -> Any:
        client = _client()
        if client is None:
            return await old_get_response_async(self, request)

        trace_id = uuid.uuid4().hex
        client.scope.set_trace_id(trace_id)
        from .request import build_request_ctx

        ctx = build_request_ctx(request, client.send_default_pii)
        client.scope.set_request(ctx)

        start = time.perf_counter()
        response = None
        status_code: int | None = None
        try:
            response = await old_get_response_async(self, request)
            status_code = getattr(response, "status_code", None)
            return response
        finally:
            _finalize_request_cycle(
                request,
                start=start,
                response=response,
                status_code=status_code,
                trace_id=trace_id,
            )

    BaseHandler.get_response = patched_get_response  # type: ignore[method-assign]
    BaseHandler.get_response_async = patched_get_response_async  # type: ignore[method-assign]
    _patched = True
