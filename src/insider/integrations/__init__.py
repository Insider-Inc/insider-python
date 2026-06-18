"""
Framework integrations for Insider.

Each integration exposes a `setup_once()` hook that patches into the host
framework exactly once per process. Pass instances to `insider.init`:

    insider.init(dsn=..., integrations=[DjangoIntegration()])
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .logging import LoggingIntegration

__all__ = ["Integration", "LoggingIntegration"]


@runtime_checkable
class Integration(Protocol):
    """Minimal integration contract."""

    def setup_once(self) -> None:
        """Install hooks into the host framework. Idempotent."""
