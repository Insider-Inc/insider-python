"""Stdlib logging handler — buffers logs into request envelope or emits standalone."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ...client import _client
from ...safety import safe
from .levels import insider_level

if TYPE_CHECKING:
    from . import LoggingIntegration


_INTERNAL_LOGGER_PREFIXES = (
    "django.utils.autoreload",
    "django.server",
    "django.template",
    "werkzeug",
)


class InsiderLoggingHandler(logging.Handler):
    """Attach to the root logger via `LoggingIntegration`."""

    def __init__(self, integration: LoggingIntegration) -> None:
        super().__init__(level=logging.NOTSET)
        self._integration = integration

    @safe
    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("insider"):
            return
        if any(record.name.startswith(prefix) for prefix in _INTERNAL_LOGGER_PREFIXES):
            return

        client = _client()
        if client is None:
            return

        message = record.getMessage()
        if not message:
            return

        level = insider_level(record)
        source = record.name
        timestamp = _record_iso(record)

        if record.levelno >= self._integration._breadcrumb_level_no:
            client.scope.add_breadcrumb(
                level=level,
                message=message,
                category=source,
                timestamp=timestamp,
            )

        if not client.enable_logs:
            return
        if record.levelno < self._integration._logs_level_no:
            return

        if client.scope.current_request() is not None:
            client.scope.add_request_log(
                level=level,
                message=message,
                source=source,
                timestamp=timestamp,
            )


def _record_iso(record: logging.LogRecord) -> str:
    return datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
