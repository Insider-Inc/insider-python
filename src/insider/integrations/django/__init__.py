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
"""

from __future__ import annotations

import threading

from ...safety import debug, safe
from . import drf, handler, signals, wsgi


class DjangoIntegration:
    """Patch Django's request/exception path for automatic error capture."""

    identifier = "django"

    _lock = threading.Lock()
    _installed = False

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
        handler.install()
        wsgi.install()
        drf.install()
