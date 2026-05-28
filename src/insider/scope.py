"""
Global + per-thread scope.

The scope holds the context that every Beacon should be enriched with:

  - Static, set once at `init()`: environment, release, in_app_include.
  - Dynamic, per-thread: the current HTTP request (when running inside a
    framework integration), other transient enrichments.

We use a threading.local for the dynamic part because Django still runs
one request per thread under wsgi. When we add asgi / asyncio support in
a later phase we'll swap this for `contextvars.ContextVar` — the public
API doesn't change.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StaticScope:
    """Process-global, set by `Client.__init__` and read-only thereafter."""

    environment: str = "production"
    release: Optional[str] = None
    in_app_include: Optional[List[str]] = None


class _ThreadLocal(threading.local):
    """Per-thread state. Each thread gets its own `request` slot."""

    request: Optional[Dict[str, Any]] = None


@dataclass
class Scope:
    static: StaticScope = field(default_factory=StaticScope)
    _local: _ThreadLocal = field(default_factory=_ThreadLocal)

    # -- request context ---------------------------------------------------

    def set_request(self, request: Dict[str, Any]) -> None:
        """Attach a request-context dict to the current thread."""
        self._local.request = request

    def clear_request(self) -> None:
        """Drop the current thread's request context."""
        self._local.request = None

    def current_request(self) -> Optional[Dict[str, Any]]:
        return getattr(self._local, "request", None)
