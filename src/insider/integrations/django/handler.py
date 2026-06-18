"""
Patch `BaseHandler.get_response` for request context and auto perf timing.

We patch `get_response` (not middleware) because:

  - Customers already init in `wsgi.py` without touching INSTALLED_APPS.
  - The patch wraps the entire handler, including middleware inside Django's
    request cycle.
  - Perf timing in `finally` runs once per request whether the view returns
    200 or raises (converted to 500 by Django).
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable

from ...client import _client
from ...safety import debug, safe
from .perf import emit_request_envelope
from .request import build_request_ctx

_patched = False
_auto_perf = True


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

    @safe
    def patched_get_response(self: Any, request: Any) -> Any:
        client = _client()
        if client is None:
            return old_get_response(self, request)

        trace_id = uuid.uuid4().hex
        client.scope.set_trace_id(trace_id)
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
            duration_ms = (time.perf_counter() - start) * 1000.0
            if _auto_perf:
                emit_request_envelope(
                    request,
                    duration_ms=duration_ms,
                    status_code=status_code,
                    trace_id=trace_id,
                )
            client.scope.clear_request_cycle()

    BaseHandler.get_response = patched_get_response  # type: ignore[method-assign]
    _patched = True
