"""
Build Insider request-context dicts from Django (and DRF) request objects.
"""

from __future__ import annotations

import weakref
from typing import Any, Dict, Optional

from ...safety import debug

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

_DRF_BACKREF_ATTR = "_insider_drf_request_backref"


def attach_drf_request_backref(django_request: Any, drf_request: Any) -> None:
    """Link a DRF Request to its wrapped Django request for body reads."""
    try:
        setattr(django_request, _DRF_BACKREF_ATTR, weakref.ref(drf_request))
    except Exception as exc:
        debug(f"drf request backref failed: {exc}")


def build_request_ctx_from_scope(
    scope: Any,
    send_default_pii: bool,
) -> Dict[str, Any]:
    """Build request context from a raw ASGI HTTP scope."""
    try:
        headers: Dict[str, str] = {}
        for key, value in scope.get("headers") or []:
            try:
                name = key.decode("latin-1").lower().replace("_", "-")
                val = value.decode("latin-1")
            except Exception:
                continue
            if name not in _SAFE_HEADERS and len(val) > 4096:
                continue
            headers[name] = val

        query_raw = scope.get("query_string") or b""
        query = (
            query_raw.decode("latin-1", errors="replace") if query_raw else None
        )
        path = scope.get("path")
        method = scope.get("method")
        client = scope.get("client")
        ip = client[0] if client else None

        ctx: Dict[str, Any] = {
            "method": method,
            "path": path,
            "query_string": query,
            "headers": headers,
            "ip": ip,
        }
        if send_default_pii and ip:
            ctx["ip_address"] = ip
        return ctx
    except Exception as exc:
        debug(f"asgi scope ctx build failed: {exc}")
        return {}


def build_request_ctx(request: Any, send_default_pii: bool) -> Dict[str, Any]:
    try:
        request = _resolve_drf_request(request)

        method = getattr(request, "method", None)
        path = getattr(request, "path", None)
        meta = getattr(request, "META", {})
        query = meta.get("QUERY_STRING") or None
        route = None
        try:
            match = getattr(request, "resolver_match", None)
            if match is not None:
                route = match.view_name
        except Exception:
            pass

        headers = _extract_headers(meta)

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


def _resolve_drf_request(request: Any) -> Any:
    """Prefer the DRF Request when a weak backref was attached in `initial`."""
    try:
        backref = getattr(request, _DRF_BACKREF_ATTR, None)
        if backref is not None:
            drf_request = backref()
            if drf_request is not None:
                return drf_request
    except Exception:
        pass
    return request


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
        data = getattr(request, "data", None)
        if data is not None and not isinstance(data, (str, bytes)):
            try:
                import json

                return json.dumps(data)
            except Exception:
                return str(data)

        raw = getattr(request, "body", None)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return str(raw)
    except Exception:
        return None


_RESPONSE_BODY_MAX_BYTES = 8192


def read_response_body(response: Any, *, max_bytes: int = _RESPONSE_BODY_MAX_BYTES) -> Optional[str]:
    """Return response content as text when already materialized on the response."""
    if response is None:
        return None
    try:
        from django.http import StreamingHttpResponse

        if isinstance(response, StreamingHttpResponse):
            return None
    except Exception:
        pass
    try:
        content = getattr(response, "content", None)
        if content is None:
            return None
        if not isinstance(content, (bytes, bytearray)):
            return str(content)
        raw = bytes(content)
        if len(raw) > max_bytes:
            raw = raw[:max_bytes]
            suffix = "...[truncated]"
        else:
            suffix = ""
        return raw.decode("utf-8", errors="replace") + suffix
    except Exception:
        return None


def format_request_user(user_val: Any) -> str:
    if not user_val:
        return "anonymous"
    if isinstance(user_val, dict):
        uid = user_val.get("id")
        if uid is not None:
            return str(uid)
    return str(user_val)
