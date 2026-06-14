"""
InsiderMiddleware: attach request context to the SDK scope, and
auto-capture any unhandled exception that escapes a view.

The middleware is a no-op when the SDK is in disabled mode.

Prefer the Sentry-style integration instead — see
`insider.integrations.django.DjangoIntegration` and `wsgi.py` init.
This middleware remains for backward compatibility.

What we attach to the scope:

  - method, path, route (URL name if available), query_string
  - headers (post-scrubbing — note that scrubbing happens at envelope
    build time, not here, so headers go on as-is and get masked just
    before transport)
  - body and user.id ONLY when `send_default_pii=True` in init()

What we never touch:

  - request.session
  - file uploads
  - anything from request.META not on the allowlist

`process_exception` is Django's hook for "an exception escaped a view
without being handled". We call `capture_exception` and then return
None so Django continues its normal 500 handling.
"""

from __future__ import annotations

from typing import Any, Callable

from ...client import _client
from ...integrations.django.capture import capture_request_exception
from ...integrations.django.request import build_request_ctx
from ...safety import safe


class InsiderMiddleware:
    """
    Django middleware. Installs request context on the SDK scope, then
    captures any unhandled exception with that context attached.
    """

    def __init__(self, get_response: Callable[[Any], Any]) -> None:
        self.get_response = get_response

    @safe
    def __call__(self, request: Any) -> Any:
        client = _client()
        if client is None:
            return self.get_response(request)

        ctx = build_request_ctx(request, client.send_default_pii)
        client.scope.set_request(ctx)
        try:
            return self.get_response(request)
        finally:
            client.scope.clear_request()

    @safe
    def process_exception(self, request: Any, exception: BaseException) -> None:
        capture_request_exception(request, exception)
        return None
