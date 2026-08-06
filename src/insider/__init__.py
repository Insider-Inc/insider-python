"""
Insider — Python SDK.

Public API:

    insider.init(dsn=..., environment=..., release=..., ...)
    insider.capture_exception(exc, level="error", tags=..., extra=...)
    insider.capture_message("text", level="info", tags=..., extra=...)
    insider.capture_log("text", level="info", ...)
    insider.capture_perf("GET /api/users/", duration_ms=45, status_code=200)
    insider.flush(timeout=2.0)
    insider.close(timeout=2.0)
    insider.Client, insider.DSN, insider.InvalidDSNError
    insider.LoggingIntegration
    insider.__version__

Django integration (import from subpackage):

    from insider.integrations.django import DjangoIntegration, wrap_asgi_application

Nothing else is part of the public contract. Anything imported below
`_` is internal and may change without notice.
"""

from ._version import __version__
from .client import (
    Client,
    capture_exception,
    capture_log,
    capture_message,
    capture_perf,
    close,
    flush,
    init,
)
from .dsn import DSN, InvalidDSNError
from .integrations.logging import LoggingIntegration

__all__ = [
    "Client",
    "DSN",
    "InvalidDSNError",
    "__version__",
    "capture_exception",
    "capture_log",
    "capture_message",
    "capture_perf",
    "close",
    "flush",
    "init",
    "LoggingIntegration",
]
