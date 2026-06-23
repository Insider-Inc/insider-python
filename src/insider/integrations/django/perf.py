"""
Emit one request lifecycle beacon after each Django HTTP request.

Timing runs in the `get_response` patch (handler.py) so we measure the full
view + middleware stack without adding Insider middleware to INSTALLED_APPS.
"""

from __future__ import annotations

from typing import Any, Optional

from ...client import _client
from ...safety import safe


@safe
def emit_http_footprint(
    *,
    path: str,
    method: Optional[str],
    duration_ms: float,
    status_code: Optional[int],
    trace_id: Optional[str],
) -> None:
    """Build and ship a single `kind=request` beacon for this HTTP cycle."""
    client = _client()
    if client is None:
        return

    op = path or "unknown"
    client.capture_request(
        duration_ms=duration_ms,
        op=op,
        status_code=status_code,
        method=method,
        trace_id=trace_id,
    )


@safe
def emit_request_envelope(
    request: Any,
    *,
    duration_ms: float,
    status_code: Optional[int],
    trace_id: Optional[str],
) -> None:
    """Build and ship a single `kind=request` beacon from a Django request."""
    emit_http_footprint(
        path=getattr(request, "path", None) or "unknown",
        method=getattr(request, "method", None),
        duration_ms=duration_ms,
        status_code=status_code,
        trace_id=trace_id,
    )
