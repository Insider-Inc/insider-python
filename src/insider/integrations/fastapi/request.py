"""Build Insider request-context dicts from an ASGI HTTP scope."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...safety import debug
from ...scrubbing import scrub_header_map

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


def build_request_ctx(
    scope: Dict[str, Any],
    send_default_pii: bool,
    *,
    header_policy: str = "allowlist",
    header_scrub_names: Optional[List[str]] = None,
    scrub_defaults: bool = False,
) -> Dict[str, Any]:
    """Build request context from a raw ASGI HTTP scope. Never raises."""
    try:
        headers = _extract_headers(
            scope,
            header_policy=header_policy,
            header_scrub_names=header_scrub_names,
            scrub_defaults=scrub_defaults,
        )
        query_raw = scope.get("query_string") or b""
        query = query_raw.decode("latin-1", errors="replace") if query_raw else None
        client = scope.get("client")
        ip = client[0] if client else None
        ctx: Dict[str, Any] = {
            "method": scope.get("method"),
            "path": scope.get("path"),
            "query_string": query,
            "headers": headers,
            "ip": ip,
        }
        if send_default_pii and ip:
            ctx["ip_address"] = ip
        return ctx
    except Exception as exc:
        debug(f"fastapi request ctx build failed: {exc}")
        return {}


def user_payload_from_scope(scope: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return ``{"id": ...}`` when the ASGI scope carries an authenticated user."""
    try:
        user = scope.get("user")
        if user is None:
            state = scope.get("state")
            if isinstance(state, dict):
                user = state.get("user")
            else:
                user = getattr(state, "user", None)
        return _user_payload(user)
    except Exception as exc:
        debug(f"fastapi user read failed: {exc}")
        return None


def _user_payload(user: Any) -> Optional[Dict[str, Any]]:
    if user is None:
        return None
    if isinstance(user, dict):
        if user.get("is_authenticated") is False:
            return None
        user_id = user.get("id")
        if user_id is None:
            return None
        return {"id": user_id}
    if getattr(user, "is_authenticated", True) is False:
        return None
    user_id = getattr(user, "id", None)
    if user_id is None:
        return None
    return {"id": user_id}


def _extract_headers(
    scope: Dict[str, Any],
    *,
    header_policy: str,
    header_scrub_names: Optional[List[str]],
    scrub_defaults: bool,
) -> Dict[str, str]:
    if header_policy == "none":
        return {}
    headers: Dict[str, str] = {}
    for key, value in scope.get("headers") or []:
        try:
            name = key.decode("latin-1").lower().replace("_", "-")
            val = value.decode("latin-1")
        except Exception:
            continue
        if header_policy == "allowlist" and name not in _SAFE_HEADERS:
            continue
        if len(val) > 4096:
            continue
        headers[name] = val
    if header_policy == "all":
        return scrub_header_map(
            headers,
            extra_names=header_scrub_names,
            use_defaults=scrub_defaults,
        )
    return headers
