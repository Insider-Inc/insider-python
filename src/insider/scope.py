"""
Global + per-thread scope.

The scope holds the context that every Footprint should be enriched with:

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
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

BREADCRUMB_MAX = 50
REQUEST_LOG_MAX = 100


@dataclass(frozen=True)
class Breadcrumb:
    level: str
    message: str
    category: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "message": self.message,
            "category": self.category,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class RequestLogLine:
    level: str
    message: str
    source: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "message": self.message,
            "source": self.source,
            "timestamp": self.timestamp,
        }


@dataclass
class StaticScope:
    """Process-global, set by `Client.__init__` and read-only thereafter."""

    environment: str = "production"
    release: Optional[str] = None
    in_app_include: Optional[List[str]] = None


class _ThreadLocal(threading.local):
    """Per-thread state. Each thread gets its own `request` and `trace_id` slots."""

    request: Optional[Dict[str, Any]] = None
    trace_id: Optional[str] = None
    pending_exception: Optional[Dict[str, Any]] = None
    breadcrumbs: Deque[Breadcrumb]
    request_logs: Deque[RequestLogLine]


@dataclass
class Scope:
    static: StaticScope = field(default_factory=StaticScope)
    _local: _ThreadLocal = field(default_factory=_ThreadLocal)

    def __post_init__(self) -> None:
        if not hasattr(self._local, "breadcrumbs") or self._local.breadcrumbs is None:
            self._local.breadcrumbs = deque(maxlen=BREADCRUMB_MAX)
        if not hasattr(self._local, "request_logs") or self._local.request_logs is None:
            self._local.request_logs = deque(maxlen=REQUEST_LOG_MAX)

    # -- request context ---------------------------------------------------

    def set_request(self, request: Dict[str, Any]) -> None:
        """Attach a request-context dict to the current thread."""
        self._local.request = request

    def clear_request(self) -> None:
        """Drop the current thread's request context."""
        self._local.request = None

    def current_request(self) -> Optional[Dict[str, Any]]:
        return getattr(self._local, "request", None)

    # -- trace id (links perf + error beacons on one HTTP request) ---------

    def set_trace_id(self, trace_id: str) -> None:
        """Attach a trace id for the current thread (set by DjangoIntegration)."""
        self._local.trace_id = trace_id

    def clear_trace_id(self) -> None:
        self._local.trace_id = None

    def current_trace_id(self) -> Optional[str]:
        return getattr(self._local, "trace_id", None)

    # -- breadcrumbs (log context on errors) -------------------------------

    def add_breadcrumb(
        self,
        *,
        level: str,
        message: str,
        category: str,
        timestamp: str,
    ) -> None:
        if not hasattr(self._local, "breadcrumbs") or self._local.breadcrumbs is None:
            self._local.breadcrumbs = deque(maxlen=BREADCRUMB_MAX)
        self._local.breadcrumbs.append(
            Breadcrumb(
                level=level,
                message=message,
                category=category,
                timestamp=timestamp,
            )
        )

    def current_breadcrumbs(self) -> List[Dict[str, Any]]:
        crumbs = getattr(self._local, "breadcrumbs", None)
        if not crumbs:
            return []
        return [c.to_dict() for c in crumbs]

    def clear_breadcrumbs(self) -> None:
        logs = getattr(self._local, "breadcrumbs", None)
        if logs is not None:
            logs.clear()

    # -- pending exception (buffered until request envelope emit) ----------

    def set_pending_exception(self, exception_block: Dict[str, Any]) -> None:
        self._local.pending_exception = exception_block

    def current_pending_exception(self) -> Optional[Dict[str, Any]]:
        return getattr(self._local, "pending_exception", None)

    def clear_pending_exception(self) -> None:
        self._local.pending_exception = None

    # -- request-scoped logs (flushed into request envelope) -----------------

    def add_request_log(
        self,
        *,
        level: str,
        message: str,
        source: str,
        timestamp: str,
    ) -> None:
        if not hasattr(self._local, "request_logs") or self._local.request_logs is None:
            self._local.request_logs = deque(maxlen=REQUEST_LOG_MAX)
        self._local.request_logs.append(
            RequestLogLine(
                level=level,
                message=message,
                source=source,
                timestamp=timestamp,
            )
        )

    def current_request_logs(self) -> List[Dict[str, Any]]:
        lines = getattr(self._local, "request_logs", None)
        if not lines:
            return []
        return [line.to_dict() for line in lines]

    def clear_request_logs(self) -> None:
        lines = getattr(self._local, "request_logs", None)
        if lines is not None:
            lines.clear()

    def clear_request_cycle(self) -> None:
        """Drop all per-request thread state after a request envelope is emitted."""
        self.clear_request()
        self.clear_trace_id()
        self.clear_pending_exception()
        self.clear_request_logs()
        self.clear_breadcrumbs()
