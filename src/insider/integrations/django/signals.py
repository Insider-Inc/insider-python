"""
Connect Django's exception path to Insider capture.

Patches ``response_for_exception`` so the exception object is captured
reliably on both WSGI and ASGI (``got_request_exception`` alone is not
enough — ``sys.exc_info()`` is often cleared before the signal handler runs).
"""

from __future__ import annotations

import sys
from typing import Any, Tuple, Type

from ...safety import debug, safe
from .capture import capture_request_exception

_connected = False
_rfe_patched = False

# These are converted to 4xx responses without emitting got_request_exception.
_HANDLED_QUIETLY: Tuple[Type[BaseException], ...] = ()


def install() -> None:
    global _connected, _rfe_patched, _HANDLED_QUIETLY
    if _connected and _rfe_patched:
        return
    try:
        from django.core import signals
        from django.core.exceptions import (
            BadRequest,
            PermissionDenied,
            SuspiciousOperation,
        )
        from django.core.handlers import exception as exception_module
        from django.http import Http404
        from django.http.multipartparser import MultiPartParserError
    except ImportError:
        debug("django signals unavailable; skipping exception hooks")
        return

    _HANDLED_QUIETLY = (
        Http404,
        PermissionDenied,
        MultiPartParserError,
        BadRequest,
        SuspiciousOperation,
    )

    if not _rfe_patched:
        old_rfe = exception_module.response_for_exception

        @safe
        def patched_rfe(request: Any, exc: BaseException) -> Any:
            response = old_rfe(request, exc)
            if not isinstance(exc, _HANDLED_QUIETLY) and getattr(
                response, "status_code", 500
            ) >= 500:
                capture_request_exception(request, exc)
            return response

        exception_module.response_for_exception = patched_rfe  # type: ignore[attr-defined]
        _rfe_patched = True

    if not _connected:
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
