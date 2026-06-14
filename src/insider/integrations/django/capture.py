"""
Shared request-exception capture with de-duplication.
"""

from __future__ import annotations

from typing import Any

from ... import capture_exception
from ...client import _client
from ...safety import safe
from .request import build_request_ctx

_CAPTURED_ATTR = "_insider_exception_captured"


@safe
def capture_request_exception(request: Any, exception: BaseException) -> None:
    """
    Capture an unhandled request exception once per request.

    Middleware `process_exception` and Django's `got_request_exception`
    signal can both fire for the same failure; the request flag prevents
    double-beaming.
    """
    if getattr(request, _CAPTURED_ATTR, False):
        return
    setattr(request, _CAPTURED_ATTR, True)

    client = _client()
    if client is None:
        return

    # Scope may already be set by middleware or the get_response patch.
    if client.scope.current_request() is None:
        ctx = build_request_ctx(request, client.send_default_pii)
        client.scope.set_request(ctx)
        try:
            capture_exception(exception)
        finally:
            client.scope.clear_request()
    else:
        capture_exception(exception)
