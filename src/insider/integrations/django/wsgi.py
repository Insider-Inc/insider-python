"""
Patch `WSGIHandler.__call__` to capture exceptions that escape Django entirely.
"""

from __future__ import annotations

from typing import Any, Callable

from ... import capture_exception
from ...client import _client
from ...safety import debug, safe

_patched = False


def install() -> None:
    global _patched
    if _patched:
        return
    try:
        from django.core.handlers.wsgi import WSGIHandler
    except ImportError:
        debug("django WSGIHandler unavailable; skipping WSGI patch")
        return

    old_call: Callable[..., Any] = WSGIHandler.__call__

    @safe
    def patched_call(
        self: Any,
        environ: Any,
        start_response: Any,
    ) -> Any:
        if _client() is None:
            return old_call(self, environ, start_response)
        try:
            return old_call(self, environ, start_response)
        except BaseException as exc:
            capture_exception(exc)
            raise

    WSGIHandler.__call__ = patched_call  # type: ignore[method-assign]
    _patched = True
