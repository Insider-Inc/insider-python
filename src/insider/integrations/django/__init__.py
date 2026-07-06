"""
Sentry-style Django integration.

Install with `insider.init(..., integrations=[DjangoIntegration()])` in
`wsgi.py` / `asgi.py` before `get_wsgi_application()` or
`get_asgi_application()`. No middleware or `INSTALLED_APPS` wiring required.

Hooks installed (each once per process):

  - `got_request_exception` → auto-capture unhandled view errors
  - `BaseHandler.get_response` → request context on the SDK scope (WSGI + ASGI HTTP)
  - `WSGIHandler.__call__` → capture catastrophic WSGI escapes
  - `ASGIHandler.__call__` → capture catastrophic ASGI escapes
  - `APIView.initial` (when DRF is present) → DRF request body access
  - Auto `kind=request` beacon per HTTP request (optional, default on)

Channels / `ProtocolTypeRouter`: use `wrap_asgi_application()` on the HTTP
branch with `DjangoIntegration(auto_perf=False)` — see `asgi.py`.
"""

from __future__ import annotations

import threading
from typing import Any, Dict

from ...safety import debug
from . import asgi, drf, handler, signals, wsgi
from ...client import _client


class DjangoIntegration:
    """Patch Django's request/exception path — one request beacon per HTTP cycle."""

    identifier = "django"

    _lock = threading.Lock()
    _installed = False

    def __init__(self, *, auto_perf: bool = True, ignore_admin: bool = True) -> None:
        """
        Args:
            auto_perf: When True (default), emit one `kind=request` beacon
                after every HTTP request via the `get_response` patch.
                Set False when using `wrap_asgi_application()` on the HTTP
                branch of a Channels router (avoids double capture).
            ignore_admin: When True (default), skip footprints for `/admin/`
                paths in addition to SDK `ignore_paths` defaults.
        """
        self.auto_perf = auto_perf
        self.ignore_admin = ignore_admin

    def setup_once(self) -> None:
        cls = type(self)
        with cls._lock:
            if cls._installed:
                return

        try:
            import django  # noqa: F401
        except ImportError:
            debug("DjangoIntegration: django is not installed")
            return

        # Patch get_response first. Optional hooks below must not block this.
        handler.install(auto_perf=self.auto_perf)
        if not handler._patched:
            debug(
                "DjangoIntegration: get_response patch failed — "
                "call insider.init() before get_wsgi_application() / "
                "get_asgi_application()"
            )
            return

        with cls._lock:
            cls._installed = True

        if self.ignore_admin:
            client = _client()
            if client is not None:
                client.add_ignore_paths(["/admin/"])

        for label, install in (
            ("signals", signals.install),
            ("wsgi", wsgi.install),
            ("asgi", asgi.install),
            ("drf", drf.install),
        ):
            try:
                install()
            except Exception as exc:
                debug(f"DjangoIntegration: {label} hook failed: {exc}")

        _log_integration_status()

    @classmethod
    def reset_for_tests(cls) -> None:
        """Test helper — allow `setup_once()` to run again in the same process."""
        with cls._lock:
            cls._installed = False


def get_integration_status() -> Dict[str, Any]:
    """Return which Django hooks are active in this process (tests + debug)."""
    return {
        "handler": handler._patched,
        "handler_auto_perf": handler._auto_perf,
        "wsgi": wsgi._patched,
        "asgi_handler": asgi._handler_patched,
        "signals": signals._connected,
        "response_for_exception": signals._rfe_patched,
        "drf": drf._patched,
    }


def _log_integration_status() -> None:
    status = get_integration_status()
    debug(
        "DjangoIntegration: "
        + ", ".join(f"{key}={value}" for key, value in status.items())
    )


__all__ = [
    "DjangoIntegration",
    "get_integration_status",
    "wrap_asgi_application",
]

# Re-export for `from insider.integrations.django.asgi import ...`
from .asgi import wrap_asgi_application  # noqa: E402
