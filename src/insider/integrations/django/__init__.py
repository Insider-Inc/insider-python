"""
Sentry-style Django integration.

Install with `insider.init(..., integrations=[DjangoIntegration()])` in
`wsgi.py` / `asgi.py` before `get_wsgi_application()`. No middleware or
`INSTALLED_APPS` wiring required.

Hooks installed (each once per process):

  - `got_request_exception` → auto-capture unhandled view errors
  - `BaseHandler.get_response` → request context on the SDK scope
  - `WSGIHandler.__call__` → capture catastrophic escapes
  - `APIView.initial` (when DRF is present) → DRF request body access
  - Auto `kind=request` beacon per HTTP request (optional, default on)
"""

from __future__ import annotations

import threading

from ...safety import debug, safe
from . import drf, handler, signals, wsgi


class DjangoIntegration:
    """Patch Django's request/exception path — one request beacon per HTTP cycle."""

    identifier = "django"

    _lock = threading.Lock()
    _installed = False

    def __init__(self, *, auto_perf: bool = True) -> None:
        """
        Args:
            auto_perf: When True (default), emit one `kind=request` beacon
                after every HTTP request. Disable for high-traffic apps until
                server-side sampling lands.
        """
        self.auto_perf = auto_perf

    @safe
    def setup_once(self) -> None:
        cls = type(self)
        with cls._lock:
            if cls._installed:
                return
            cls._installed = True

        try:
            import django  # noqa: F401
        except ImportError:
            debug("DjangoIntegration: django is not installed")
            cls._installed = False
            return

        signals.install()
        handler.install(auto_perf=self.auto_perf)
        wsgi.install()
        drf.install()
