"""
FastAPI integration.

Install with ``insider.init(..., integrations=[FastAPIIntegration()])`` before
the app starts serving. No middleware wiring. Every HTTP request emits one
flat footprint (timing, context, logs, and any unhandled exception).

WebSocket and lifespan scopes are ignored.
"""

from __future__ import annotations

import threading
from typing import Any, Dict

from ...safety import debug
from . import asgi


class FastAPIIntegration:
    """Patch Starlette/FastAPI's ASGI entrypoint — one footprint per HTTP request."""

    identifier = "fastapi"

    _lock = threading.Lock()
    _installed = False

    def __init__(self, *, auto_perf: bool = True) -> None:
        """
        Args:
            auto_perf: When True (default), beam one footprint after every
                HTTP request. Set False to install scope hooks without
                auto-capture.
        """
        self.auto_perf = auto_perf

    def setup_once(self) -> None:
        cls = type(self)
        with cls._lock:
            if cls._installed:
                return

        try:
            import fastapi  # noqa: F401
        except ImportError:
            debug("FastAPIIntegration: fastapi is not installed")
            return

        asgi.install(auto_perf=self.auto_perf)
        if not asgi._patched:
            debug("FastAPIIntegration: ASGI patch failed")
            return

        with cls._lock:
            cls._installed = True
        _log_integration_status()

    @classmethod
    def reset_for_tests(cls) -> None:
        """Test helper — allow ``setup_once()`` to run again in the same process."""
        with cls._lock:
            cls._installed = False


def get_integration_status() -> Dict[str, Any]:
    """Return which FastAPI hooks are active in this process."""
    return {
        "asgi": asgi._patched,
        "auto_perf": asgi._auto_perf,
    }


def _log_integration_status() -> None:
    status = get_integration_status()
    debug(
        "FastAPIIntegration: "
        + ", ".join(f"{key}={value}" for key, value in status.items())
    )


__all__ = [
    "FastAPIIntegration",
    "get_integration_status",
]
