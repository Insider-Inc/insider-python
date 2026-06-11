"""
Beacon envelope construction + size-budget enforcement.

`build_envelope` is called from the capture functions in `client.py`. It
takes the raw bits (kind, level, message, exception payload, scope,
tags, extra) and produces the top-level dict the transport will ship.

`enforce_size_budget` is the second-to-last step before submit. It
truncates progressively until the JSON-encoded envelope fits under the
server's 256 KB cap. The truncation order is intentional and matches
docs/python-sdk-plan -> "Payload size budget":

    1. message capped to 8 KB
    2. frame `vars` capped to 2 KB each   (v1 has no vars, future-proof)
    3. request.body capped to 32 KB
    4. request.headers capped to 4 KB (after deny-listed keys are masked
       by scrub.py upstream)
    5. drop frames from the outermost end of the stack until envelope fits,
       keeping the innermost frames (closest to the error)
    6. drop payload.request entirely
    7. ship minimal envelope with payload.truncated = True

Step 7's existence is the property: we ship *something* truthful rather
than nothing.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from .safety import debug

MAX_ENVELOPE_BYTES = 256 * 1024
MAX_MESSAGE_BYTES = 8 * 1024
MAX_REQUEST_BODY_BYTES = 32 * 1024
MAX_REQUEST_HEADERS_BYTES = 4 * 1024


def _now_iso() -> str:
    """ISO-8601 UTC timestamp with microseconds, used as `occurred_at`."""
    return datetime.now(timezone.utc).isoformat()


def build_envelope(
    *,
    kind: str,
    level: str,
    message: Optional[str],
    source: Optional[str],
    environment: str,
    release: Optional[str],
    trace_id: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
    tags: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    occurred_at: Optional[str] = None,
    commit_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble the Beacon envelope. Pure: no I/O, no globals."""
    body: Dict[str, Any] = dict(payload or {})
    if tags:
        body["tags"] = tags
    if extra:
        body["extra"] = extra
    if commit_hash:
        body["commit_hash"] = commit_hash
    return {
        "kind": kind,
        "level": level,
        "environment": environment,
        "release": release,
        "source": source,
        "message": message,
        "occurred_at": occurred_at or _now_iso(),
        "trace_id": trace_id,
        "payload": body,
    }


# ---------------------------------------------------------------------------
# Size budget
# ---------------------------------------------------------------------------


def _byte_len(obj: Any) -> int:
    """Best-effort serialized size. Encode errors → infinity to force trim."""
    try:
        return len(json.dumps(obj, default=str, ensure_ascii=False).encode("utf-8"))
    except Exception:
        return 10**9


def _truncate_str_to_bytes(value: str, limit: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore")


def enforce_size_budget(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply the truncation rules in order. Returns the same envelope dict,
    mutated. The caller is expected to discard the original reference
    after this call.
    """
    # 1. message
    msg = envelope.get("message")
    if isinstance(msg, str):
        envelope["message"] = _truncate_str_to_bytes(msg, MAX_MESSAGE_BYTES)

    payload = envelope.get("payload") or {}

    # 3. request.body
    request_ctx = payload.get("request")
    if isinstance(request_ctx, dict):
        body = request_ctx.get("body")
        if isinstance(body, str):
            request_ctx["body"] = _truncate_str_to_bytes(body, MAX_REQUEST_BODY_BYTES)
        elif body is not None:
            # Non-string body: dump to string and cap.
            try:
                as_str = json.dumps(body, default=str)
            except Exception:
                as_str = str(body)
            request_ctx["body"] = _truncate_str_to_bytes(as_str, MAX_REQUEST_BODY_BYTES)

        # 4. request.headers
        headers = request_ctx.get("headers")
        if isinstance(headers, dict):
            if _byte_len(headers) > MAX_REQUEST_HEADERS_BYTES:
                # Drop the largest-value headers until under budget. We drop
                # whole entries rather than truncating individual values to
                # avoid producing partial / misleading header strings.
                items = sorted(
                    headers.items(),
                    key=lambda kv: _byte_len(kv[1]),
                    reverse=True,
                )
                trimmed = dict(items)
                while items and _byte_len(trimmed) > MAX_REQUEST_HEADERS_BYTES:
                    k, _ = items.pop(0)
                    trimmed.pop(k, None)
                request_ctx["headers"] = trimmed

    # 5. drop frames from the outside until envelope fits
    exception = payload.get("exception")
    if isinstance(exception, dict) and isinstance(exception.get("frames"), list):
        while _byte_len(envelope) > MAX_ENVELOPE_BYTES and exception["frames"]:
            # Keep the *innermost* frames (the end of the list).
            exception["frames"].pop(0)

    # 6. drop payload.request entirely if still too big
    if _byte_len(envelope) > MAX_ENVELOPE_BYTES and "request" in payload:
        payload.pop("request", None)
        debug("size budget: dropped payload.request")

    # 7. minimal envelope of last resort
    if _byte_len(envelope) > MAX_ENVELOPE_BYTES:
        minimal_exception: Optional[Dict[str, Any]] = None
        if isinstance(exception, dict):
            minimal_exception = {
                "type": exception.get("type"),
                "value": _truncate_str_to_bytes(
                    str(exception.get("value", "")), 1024
                ),
            }
        minimal_payload: Dict[str, Any] = {"truncated": True}
        if minimal_exception is not None:
            minimal_payload["exception"] = minimal_exception
        envelope["payload"] = minimal_payload
        debug("size budget: emitting minimal envelope")

    return envelope


def safe_frame_subset(
    frames: List[Dict[str, Any]],
    in_app_only: bool = False,
) -> List[Dict[str, Any]]:
    """Optional filter for dashboards; unused in v1 but kept for callers."""
    if not in_app_only:
        return frames
    return [f for f in frames if f.get("in_app")]


__all__: Iterable[str] = (
    "MAX_ENVELOPE_BYTES",
    "build_envelope",
    "enforce_size_budget",
)
