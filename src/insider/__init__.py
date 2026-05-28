"""
Insider — Python SDK.

Public API:

    insider.init(dsn=..., environment=..., release=..., ...)
    insider.capture_exception(exc, level="error", tags=..., extra=...)
    insider.capture_message("text", level="info", tags=..., extra=...)
    insider.flush(timeout=2.0)
    insider.close(timeout=2.0)

Nothing else is part of the public contract. Anything imported below
`_` is internal and may change without notice.
"""

from ._version import __version__
from .client import (
    Client,
    capture_exception,
    capture_message,
    close,
    flush,
    init,
)
from .dsn import DSN, InvalidDSNError

__all__ = [
    "Client",
    "DSN",
    "InvalidDSNError",
    "__version__",
    "capture_exception",
    "capture_message",
    "close",
    "flush",
    "init",
]
