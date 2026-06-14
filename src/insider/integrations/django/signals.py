"""
Connect Django's `got_request_exception` signal to Insider capture.
"""

from __future__ import annotations

import sys
from typing import Any

from ...safety import debug, safe
from .capture import capture_request_exception

_connected = False


def install() -> None:
    global _connected
    if _connected:
        return
    try:
        from django.core import signals
    except ImportError:
        debug("django signals unavailable; skipping got_request_exception hook")
        return

    signals.got_request_exception.connect(_on_got_request_exception)
    _connected = True


@safe
def _on_got_request_exception(
    sender: Any,
    request: Any,
    **kwargs: Any,
) -> None:
    exc = sys.exc_info()[1]
    if exc is None:
        return
    capture_request_exception(request, exc)
