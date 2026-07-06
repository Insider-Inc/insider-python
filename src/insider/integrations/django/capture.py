"""
Shared request-exception capture with de-duplication.

Unhandled exceptions during an HTTP request are buffered on the scope and
included in the single `kind=request` envelope emitted in `finally` — not
beamed as a separate `kind=error` row.
"""

from __future__ import annotations

from typing import Any

from ...client import _client
from ...safety import safe
from ...stacktrace import exception_payload
from .request import build_request_ctx
from ._client_ctx import request_ctx_kwargs

_CAPTURED_ATTR = "_insider_exception_captured"
_PENDING_BLOCK_ATTR = "_insider_pending_exception_block"


def sync_pending_from_request(request: Any) -> None:
    """Copy exception buffered on the request (async worker thread) onto scope."""
    client = _client()
    if client is None:
        return
    if client.scope.current_pending_exception() is not None:
        return
    block = getattr(request, _PENDING_BLOCK_ATTR, None)
    if block is not None:
        client.scope.set_pending_exception(block)


@safe
def capture_request_exception(request: Any, exception: BaseException) -> None:
    """
    Buffer an unhandled request exception once per request.

    Middleware `process_exception` and Django's `got_request_exception`
    signal can both fire for the same failure; the request flag prevents
    double-buffering.
    """
    if getattr(request, _CAPTURED_ATTR, False):
        return
    setattr(request, _CAPTURED_ATTR, True)

    client = _client()
    if client is None:
        return

    if client.scope.current_request() is None:
        ctx = build_request_ctx(request, client.send_default_pii, **request_ctx_kwargs())
        client.scope.set_request(ctx)

    block = exception_payload(
        exception, in_app_include=client.scope.static.in_app_include
    )
    setattr(request, _PENDING_BLOCK_ATTR, block)
    client.scope.set_pending_exception(block)
