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
def emit_request_envelope(
    request: Any,
    *,
    duration_ms: float,
    status_code: Optional[int],
    trace_id: Optional[str],
) -> None:
    """Build and ship a single `kind=request` beacon for this HTTP cycle."""
    client = _client()
    if client is None:
        return

    method = getattr(request, "method", None)
    op = getattr(request, "path", None) or "unknown"

    client.capture_request(
        duration_ms=duration_ms,
        op=op,
        status_code=status_code,
        method=method,
        trace_id=trace_id,
    )
