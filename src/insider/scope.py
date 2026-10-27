"""
Global + per-task scope.

The scope holds the context that every Footprint should be enriched with:

  - Static, set once at `init()`: environment, release, in_app_include.
  - Dynamic, per task: the current HTTP request (when running inside a
    framework integration), other transient enrichments.

Dynamic state lives in a `contextvars.ContextVar`. Each OS thread has its
own context, which matches Django's one-request-per-thread WSGI model.
Async servers copy that context into each request task, so concurrent
FastAPI/ASGI requests on one event loop do not share footprints.
"""

from __future__ import annotations

import contextvars
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


class _Dynamic:
    """Mutable per-task request state. Not shared across contexts."""

    __slots__ = (
        "request",
        "trace_id",
        "pending_exception",
        "breadcrumbs",
        "request_logs",
    )

    def __init__(self) -> None:
        self.request: Optional[Dict[str, Any]] = None
        self.trace_id: Optional[str] = None
        self.pending_exception: Optional[Dict[str, Any]] = None
        self.breadcrumbs: Deque[Breadcrumb] = deque(maxlen=BREADCRUMB_MAX)
        self.request_logs: Deque[RequestLogLine] = deque(maxlen=REQUEST_LOG_MAX)


@dataclass
class Scope:
    static: StaticScope = field(default_factory=StaticScope)
    _dynamic: contextvars.ContextVar = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._dynamic = contextvars.ContextVar(f"insider_scope_{id(self)}")

    def _state(self) -> _Dynamic:
        try:
            return self._dynamic.get()
        except LookupError:
            state = _Dynamic()
            self._dynamic.set(state)
            return state

    # -- request context ---------------------------------------------------

    def set_request(self, request: Dict[str, Any]) -> None:
        """Attach a request-context dict to the current task."""
        self._state().request = request

    def clear_request(self) -> None:
        """Drop the current task's request context."""
        self._state().request = None

    def current_request(self) -> Optional[Dict[str, Any]]:
        return self._state().request

    # -- trace id (links perf + error beacons on one HTTP request) ---------

    def set_trace_id(self, trace_id: str) -> None:
        """Attach a trace id for the current task (set by framework integrations)."""
        self._state().trace_id = trace_id

    def clear_trace_id(self) -> None:
        self._state().trace_id = None

    def current_trace_id(self) -> Optional[str]:
        return self._state().trace_id

    # -- breadcrumbs (log context on errors) -------------------------------

    def add_breadcrumb(
        self,
        *,
        level: str,
        message: str,
        category: str,
        timestamp: str,
    ) -> None:
        self._state().breadcrumbs.append(
            Breadcrumb(
                level=level,
                message=message,
                category=category,
                timestamp=timestamp,
            )
        )

    def current_breadcrumbs(self) -> List[Dict[str, Any]]:
        return [crumb.to_dict() for crumb in self._state().breadcrumbs]

    def clear_breadcrumbs(self) -> None:
        self._state().breadcrumbs.clear()

    # -- pending exception (buffered until request envelope emit) ----------

    def set_pending_exception(self, exception_block: Dict[str, Any]) -> None:
        self._state().pending_exception = exception_block

    def current_pending_exception(self) -> Optional[Dict[str, Any]]:
        return self._state().pending_exception

    def clear_pending_exception(self) -> None:
        self._state().pending_exception = None

    # -- request-scoped logs (flushed into request envelope) -----------------

    def add_request_log(
        self,
        *,
        level: str,
        message: str,
        source: str,
        timestamp: str,
    ) -> None:
        self._state().request_logs.append(
            RequestLogLine(
                level=level,
                message=message,
                source=source,
                timestamp=timestamp,
            )
        )

    def current_request_logs(self) -> List[Dict[str, Any]]:
        return [line.to_dict() for line in self._state().request_logs]

    def clear_request_logs(self) -> None:
        self._state().request_logs.clear()

    def clear_request_cycle(self) -> None:
        """Drop all per-request task state after a request footprint is emitted."""
        self.clear_request()
        self.clear_trace_id()
        self.clear_pending_exception()
        self.clear_request_logs()
        self.clear_breadcrumbs()
