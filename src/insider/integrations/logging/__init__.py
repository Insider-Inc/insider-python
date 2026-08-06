"""
Stdlib logging integration (Sentry-style).

    insider.init(
        dsn="...",
        enable_logs=True,
        integrations=[DjangoIntegration(), LoggingIntegration()],
    )

    import logging
    logging.getLogger(__name__).info("hello")  # → kind=log beacon

Django note
-----------
Apps almost always call ``insider.init()`` *before*
``get_wsgi_application()``. Django then runs ``logging.config.dictConfig``
from ``settings.LOGGING``, which **replaces** root handlers and would
drop our handler. We patch ``dictConfig`` / ``fileConfig`` so the
handler is re-attached automatically — integrators do not re-init.
"""

from __future__ import annotations

import logging
import logging.config
import threading
from typing import Any, Callable, Optional

from ...safety import debug, safe
from .handler import InsiderLoggingHandler
from .levels import logging_level

_active_integration: Optional["LoggingIntegration"] = None
_dict_config_patched = False
_file_config_patched = False
_original_dict_config: Callable[..., Any] | None = None
_original_file_config: Callable[..., Any] | None = None


@safe
def ensure_handler_attached() -> bool:
    """
    Ensure the Insider logging handler is on the root logger.

    Safe to call after Django (or anyone) runs ``dictConfig``. Returns
    True when a handler is present afterward.
    """
    integration = _active_integration
    if integration is None:
        return False
    return integration.attach_handler()


def _patch_logging_config() -> None:
    """Re-attach our handler whenever stdlib logging is reconfigured."""
    global _dict_config_patched, _file_config_patched
    global _original_dict_config, _original_file_config

    if not _dict_config_patched:
        _original_dict_config = logging.config.dictConfig

        def _dict_config_wrapper(config: Any) -> None:
            assert _original_dict_config is not None
            _original_dict_config(config)
            ensure_handler_attached()

        logging.config.dictConfig = _dict_config_wrapper  # type: ignore[assignment]
        _dict_config_patched = True
        debug("LoggingIntegration: patched logging.config.dictConfig")

    if not _file_config_patched and hasattr(logging.config, "fileConfig"):
        _original_file_config = logging.config.fileConfig

        def _file_config_wrapper(*args: Any, **kwargs: Any) -> Any:
            assert _original_file_config is not None
            result = _original_file_config(*args, **kwargs)
            ensure_handler_attached()
            return result

        logging.config.fileConfig = _file_config_wrapper  # type: ignore[assignment]
        _file_config_patched = True


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
        global _active_integration
        cls = type(self)
        with cls._lock:
            first = not cls._installed
            cls._installed = True
            _active_integration = self

        self.attach_handler()
        if first:
            _patch_logging_config()

    def attach_handler(self) -> bool:
        """Add our handler to the root logger if it is not already there."""
        root = logging.getLogger()
        for existing in root.handlers:
            if getattr(existing, "_insider_handler", False):
                return True

        self._handler = InsiderLoggingHandler(self)
        self._handler._insider_handler = True  # type: ignore[attr-defined]
        # Match whatever the integration was configured for; NOTSET would
        # still respect logger levels on the record path.
        self._handler.setLevel(logging.NOTSET)
        root.addHandler(self._handler)
        debug(
            f"LoggingIntegration installed (logs>={self.logs_level}, "
            f"breadcrumbs>={self.breadcrumb_level})"
        )
        return True

    @classmethod
    def reset_for_tests(cls) -> None:
        """Test helper — undo install flags and logging.config patches."""
        global _active_integration, _dict_config_patched, _file_config_patched
        global _original_dict_config, _original_file_config

        with cls._lock:
            cls._installed = False
        _active_integration = None

        root = logging.getLogger()
        root.handlers = [
            h
            for h in root.handlers
            if not getattr(h, "_insider_handler", False)
        ]

        if _dict_config_patched and _original_dict_config is not None:
            logging.config.dictConfig = _original_dict_config  # type: ignore[assignment]
            _dict_config_patched = False
            _original_dict_config = None
        if _file_config_patched and _original_file_config is not None:
            logging.config.fileConfig = _original_file_config  # type: ignore[assignment]
            _file_config_patched = False
            _original_file_config = None
