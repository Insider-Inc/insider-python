"""
Patch `BaseHandler.get_response` to attach request context for the request lifetime.
"""

from __future__ import annotations

from typing import Any, Callable

from ...client import _client
from ...safety import debug, safe
from .request import build_request_ctx

_patched = False


def install() -> None:
    global _patched
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

        ctx = build_request_ctx(request, client.send_default_pii)
        client.scope.set_request(ctx)
        try:
            return old_get_response(self, request)
        finally:
            client.scope.clear_request()

    BaseHandler.get_response = patched_get_response  # type: ignore[method-assign]
    _patched = True
