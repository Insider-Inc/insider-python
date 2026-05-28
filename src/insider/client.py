"""
The Client and the module-level facade.

There are two ways to talk to the SDK:

  1. Module-level helpers (`insider.init`, `insider.capture_exception`,
     etc.). These operate on a single process-global `Client`.
  2. Explicit `Client` instance returned by `init()`. Useful for tests,
     advanced users, and the eventual multi-DSN case.

Both paths route to the same code. The module-level functions are thin
@safe wrappers around `_active_client()`.
"""

from __future__ import annotations

import atexit
import os
import threading
from typing import Any, Callable, Dict, Iterable, List, Optional

from ._envelope import build_envelope, enforce_size_budget
from ._version import __version__
from .dsn import DSN, InvalidDSNError
from .safety import debug, safe, set_debug
from .scope import Scope, StaticScope
from .scrubbing import scrub
from .stacktrace import caller_source, exception_payload, runtime_payload
from .transport import BackgroundTransport


VALID_KINDS = {"error", "perf", "log", "custom"}
VALID_LEVELS = {"debug", "info", "warning", "error", "fatal"}


# ---------------------------------------------------------------------------
# DSN resolution
# ---------------------------------------------------------------------------


def _resolve_dsn_string(explicit: Optional[str]) -> Optional[str]:
    """Find a DSN string from `init()` arg → env var → None."""
    if explicit:
        return explicit
    env = os.environ.get("INSIDER_DSN")
    if env:
        return env
    return None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class Client:
    """
    A configured SDK instance. Owns a `Scope`, a `BackgroundTransport`,
    and the customer-supplied hooks.

    Customers usually don't construct this directly — they call
    `insider.init(...)` which returns a `Client` and also stashes it as
    the process-global active client.
    """

    def __init__(
        self,
        dsn: DSN,
        *,
        environment: str = "production",
        release: Optional[str] = None,
        send_default_pii: bool = False,
        before_send: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]] = None,
        scrub_keys: Optional[Iterable[str]] = None,
        in_app_include: Optional[Iterable[str]] = None,
        transport_queue_size: int = 1000,
        transport_flush_timeout: float = 2.0,
        debug: bool = False,
        transport: Optional[BackgroundTransport] = None,
    ) -> None:
        set_debug(debug)
        self.dsn = dsn
        self.send_default_pii = bool(send_default_pii)
        self.before_send = before_send
        self.scrub_keys: List[str] = list(scrub_keys or [])
        self.scope = Scope(
            static=StaticScope(
                environment=environment,
                release=release,
                in_app_include=list(in_app_include) if in_app_include else None,
            )
        )
        self.transport: BackgroundTransport = transport or BackgroundTransport(
            dsn,
            queue_size=transport_queue_size,
            flush_timeout=transport_flush_timeout,
        )

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def capture_exception(
        self,
        exc: BaseException,
        *,
        level: str = "error",
        tags: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        if not isinstance(exc, BaseException):
            debug(f"capture_exception got non-exception: {type(exc).__name__}")
            return None
        level = level if level in VALID_LEVELS else "error"

        exception_block = exception_payload(
            exc, in_app_include=self.scope.static.in_app_include
        )
        payload: Dict[str, Any] = {
            "exception": exception_block,
            "runtime": runtime_payload(__version__),
        }
        request_ctx = self.scope.current_request()
        if request_ctx is not None:
            payload["request"] = request_ctx

        envelope = build_envelope(
            kind="error",
            level=level,
            message=str(exc) or type(exc).__name__,
            source=self._source_from_exception(exception_block),
            environment=self.scope.static.environment,
            release=self.scope.static.release,
            trace_id=trace_id,
            payload=payload,
            tags=tags,
            extra=extra,
        )
        return self._dispatch(envelope)

    def capture_message(
        self,
        message: str,
        *,
        level: str = "info",
        tags: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
        trace_id: Optional[str] = None,
        kind: str = "log",
    ) -> Optional[str]:
        if not isinstance(message, str):
            debug(f"capture_message expects str, got {type(message).__name__}")
            return None
        level = level if level in VALID_LEVELS else "info"
        kind = kind if kind in VALID_KINDS else "log"

        payload: Dict[str, Any] = {"runtime": runtime_payload(__version__)}
        request_ctx = self.scope.current_request()
        if request_ctx is not None:
            payload["request"] = request_ctx

        envelope = build_envelope(
            kind=kind,
            level=level,
            message=message,
            source=source or caller_source(skip=2),
            environment=self.scope.static.environment,
            release=self.scope.static.release,
            trace_id=trace_id,
            payload=payload,
            tags=tags,
            extra=extra,
        )
        return self._dispatch(envelope)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def flush(self, timeout: Optional[float] = None) -> bool:
        return self.transport.flush(timeout)

    def close(self, timeout: Optional[float] = None) -> None:
        self.transport.close(timeout)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _dispatch(self, envelope: Dict[str, Any]) -> Optional[str]:
        """Scrub → before_send → size budget → transport submit."""
        envelope["payload"] = scrub(envelope.get("payload"), extra_keys=self.scrub_keys)
        if self.before_send is not None:
            try:
                envelope = self.before_send(envelope)  # type: ignore[assignment]
            except Exception as exc:
                debug(f"before_send raised {type(exc).__name__}: {exc}; dropping beacon")
                return None
            if envelope is None:
                return None

        envelope = enforce_size_budget(envelope)
        accepted = self.transport.submit(envelope)
        return envelope.get("occurred_at") if accepted else None

    @staticmethod
    def _source_from_exception(exception_block: Dict[str, Any]) -> Optional[str]:
        """Pick the innermost in_app frame's module as the beacon `source`."""
        frames = exception_block.get("frames") or []
        for frame in reversed(frames):
            if frame.get("in_app"):
                return frame.get("module") or frame.get("function")
        if frames:
            tail = frames[-1]
            return tail.get("module") or tail.get("function")
        return None


# ---------------------------------------------------------------------------
# Module-level facade
# ---------------------------------------------------------------------------


_active_client: Optional[Client] = None
_init_lock = threading.Lock()


def _client() -> Optional[Client]:
    return _active_client


def _set_active(client: Optional[Client]) -> None:
    global _active_client
    _active_client = client


@safe
def init(
    dsn: Optional[str] = None,
    **kwargs: Any,
) -> Optional[Client]:
    """
    Initialize the SDK. Returns the new `Client` on success, or `None`
    when no DSN is configured (disabled mode).

    Calling `init` a second time is allowed but logs a warning and
    closes the previous client first. The new client becomes the
    process-global one.
    """
    global _active_client
    raw = _resolve_dsn_string(dsn)
    if not raw:
        debug("no DSN configured; entering disabled mode")
        return None
    try:
        parsed = DSN.parse(raw)
    except InvalidDSNError as exc:
        debug(f"invalid DSN: {exc}; entering disabled mode")
        return None

    with _init_lock:
        if _active_client is not None:
            debug("re-initializing; closing previous client")
            try:
                _active_client.close()
            except Exception as exc:
                debug(f"previous client close failed: {exc}")
        client = Client(parsed, **kwargs)
        _set_active(client)

    atexit.register(_atexit_close)
    return client


def _atexit_close() -> None:
    """Hook registered with `atexit` to drain on process exit."""
    client = _active_client
    if client is None:
        return
    try:
        client.close()
    except Exception as exc:
        debug(f"atexit close failed: {exc}")


@safe
def capture_exception(
    exc: BaseException,
    *,
    level: str = "error",
    tags: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None,
) -> Optional[str]:
    client = _client()
    if client is None:
        return None
    return client.capture_exception(
        exc, level=level, tags=tags, extra=extra, trace_id=trace_id
    )


@safe
def capture_message(
    message: str,
    *,
    level: str = "info",
    tags: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    source: Optional[str] = None,
    trace_id: Optional[str] = None,
    kind: str = "log",
) -> Optional[str]:
    client = _client()
    if client is None:
        return None
    return client.capture_message(
        message,
        level=level,
        tags=tags,
        extra=extra,
        source=source,
        trace_id=trace_id,
        kind=kind,
    )


@safe
def flush(timeout: Optional[float] = None) -> bool:
    client = _client()
    if client is None:
        return True
    return client.flush(timeout)


@safe
def close(timeout: Optional[float] = None) -> None:
    client = _client()
    if client is None:
        return
    client.close(timeout)
    _set_active(None)
