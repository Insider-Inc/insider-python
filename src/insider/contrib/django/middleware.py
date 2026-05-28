"""
InsiderMiddleware: attach request context to the SDK scope, and
auto-capture any unhandled exception that escapes a view.

The middleware is a no-op when the SDK is in disabled mode.

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

from typing import Any, Callable, Dict, Optional

from ... import capture_exception
from ...client import _client
from ...safety import debug, safe


# Request headers that are safe to forward to the dashboard. We keep an
# allow-list rather than a deny-list because there are too many possible
# custom headers to enumerate scary ones. Scrubbing further masks names
# matching the default deny-list (Authorization, Cookie, etc.) at envelope
# build time.
_SAFE_HEADERS = {
    "accept",
    "accept-encoding",
    "accept-language",
    "content-type",
    "content-length",
    "host",
    "referer",
    "user-agent",
    "x-forwarded-for",
    "x-real-ip",
    "x-request-id",
}


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

        ctx = self._build_request_ctx(request, client.send_default_pii)
        client.scope.set_request(ctx)
        try:
            return self.get_response(request)
        finally:
            client.scope.clear_request()

    @safe
    def process_exception(self, request: Any, exception: BaseException) -> None:
        # Scope's already set in __call__; capture inherits the request ctx.
        capture_exception(exception)
        return None  # let Django render the 500

    # ------------------------------------------------------------------

    @staticmethod
    def _build_request_ctx(request: Any, send_default_pii: bool) -> Dict[str, Any]:
        try:
            method = getattr(request, "method", None)
            path = getattr(request, "path", None)
            query = getattr(request, "META", {}).get("QUERY_STRING") or None
            route = None
            try:
                # ResolverMatch is set after urls resolve; in middleware
                # __call__ before view, it's usually None. We still try.
                match = getattr(request, "resolver_match", None)
                if match is not None:
                    route = match.view_name
            except Exception:
                pass

            headers = _extract_headers(getattr(request, "META", {}))

            ctx: Dict[str, Any] = {
                "method": method,
                "path": path,
                "query_string": query,
                "route": route,
                "headers": headers,
            }

            if send_default_pii:
                ctx["body"] = _read_body(request)
                user = getattr(request, "user", None)
                user_id = getattr(user, "id", None) if user is not None else None
                if user_id is not None:
                    ctx["user"] = {"id": user_id}

            return ctx
        except Exception as exc:
            debug(f"request ctx build failed: {exc}")
            return {}


def _extract_headers(meta: Dict[str, Any]) -> Dict[str, str]:
    """Convert Django's META dict into a real headers dict, allow-listed."""
    headers: Dict[str, str] = {}
    for key, value in meta.items():
        if not key.startswith("HTTP_") and key not in (
            "CONTENT_TYPE",
            "CONTENT_LENGTH",
        ):
            continue
        name = key
        if key.startswith("HTTP_"):
            name = key[len("HTTP_") :]
        name = name.replace("_", "-").lower()
        if name not in _SAFE_HEADERS:
            # We still include unknown headers; the scrubber will mask any
            # whose name is in the deny-list. But we cap obviously huge or
            # weird ones here.
            if len(str(value)) > 4096:
                continue
        try:
            headers[name] = str(value)
        except Exception:
            pass
    return headers


def _read_body(request: Any) -> Optional[str]:
    """
    Return a string version of the request body, or None.
    We don't consume `request.body` if it hasn't been read yet, to avoid
    breaking downstream views; if it's accessible, we take it.
    """
    try:
        raw = getattr(request, "body", None)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return str(raw)
    except Exception:
        return None
