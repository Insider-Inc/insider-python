"""
Stdlib logging integration (Sentry-style).

    insider.init(
        dsn="...",
        enable_logs=True,
        integrations=[DjangoIntegration(), LoggingIntegration()],
    )

    import logging
    logging.getLogger(__name__).info("hello")  # → kind=log beacon
"""

from __future__ import annotations

import logging
import threading

from ...safety import debug, safe
from .handler import InsiderLoggingHandler
from .levels import logging_level

_INSIDER_HANDLER = True


class LoggingIntegration:
    """Forward Python `logging` records to Insider as log beacons + breadcrumbs."""

    identifier = "logging"

    _lock = threading.Lock()
    _installed = False

    def __init__(
        self,
        *,
        logs_level: str = "INFO",
        breadcrumb_level: str = "INFO",
    ) -> None:
        self.logs_level = logs_level
        self.breadcrumb_level = breadcrumb_level
        self._logs_level_no = logging_level(logs_level)
        self._breadcrumb_level_no = logging_level(breadcrumb_level)
        self._handler: InsiderLoggingHandler | None = None

    @safe
    def setup_once(self) -> None:
        cls = type(self)
        with cls._lock:
            if cls._installed:
                return
            cls._installed = True

        root = logging.getLogger()
        for existing in root.handlers:
            if getattr(existing, "_insider_handler", False):
                debug("LoggingIntegration: handler already attached")
                return

        self._handler = InsiderLoggingHandler(self)
        self._handler._insider_handler = True  # type: ignore[attr-defined]
        root.addHandler(self._handler)
        debug(
            f"LoggingIntegration installed (logs>={self.logs_level}, "
            f"breadcrumbs>={self.breadcrumb_level})"
        )
