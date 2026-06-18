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
import subprocess
import threading
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Union

import json

from ._envelope import MAX_ENVELOPE_BYTES, build_envelope, enforce_size_budget
from ._footprint import build_footprint_payload
from ._version import __version__
from .dsn import DSN, InvalidDSNError
from .safety import debug, safe, set_debug
from .scope import Scope, StaticScope
from .scrubbing import scrub
from .stacktrace import caller_source, exception_payload, runtime_payload
from .transport import BackgroundTransport


VALID_KINDS = {"error", "perf", "log", "custom", "request"}
VALID_LEVELS = {"debug", "info", "warning", "error", "fatal"}


def _byte_len_footprint(obj: Dict[str, Any]) -> int:
    try:
        return len(json.dumps(obj, default=str, ensure_ascii=False).encode("utf-8"))
    except Exception:
        return 10**9

IntegrationLike = Union[Any, type]


def _setup_integrations(integrations: Sequence[IntegrationLike]) -> None:
    for integration in integrations:
        instance = integration() if isinstance(integration, type) else integration
        setup_once = getattr(instance, "setup_once", None)
        if callable(setup_once):
            setup_once()


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
        enable_logs: bool = False,
    ) -> None:
        set_debug(debug)
        self.dsn = dsn
        self.enable_logs = bool(enable_logs)
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
        self.commit_hash: Optional[str] = self._get_commit_hash()

        # Zero-config release tracking: if no release is provided, fallback to the git commit hash
        if not release and self.commit_hash:
            release = self.commit_hash
            self.scope.static.release = release

    def _get_commit_hash(self) -> Optional[str]:
        try:
            output = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            return output if output else None
        except Exception:
            return None

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
        if self.scope.current_request() is not None:
            self.scope.set_pending_exception(exception_block)
            return self.scope.current_trace_id()

        payload: Dict[str, Any] = {
            "exception": exception_block,
            "runtime": runtime_payload(__version__),
        }
        request_ctx = self.scope.current_request()
        if request_ctx is not None:
            payload["request"] = request_ctx
        breadcrumbs = self.scope.current_breadcrumbs()
        if breadcrumbs:
            payload["breadcrumbs"] = breadcrumbs

        envelope = build_envelope(
            kind="error",
            level=level,
            message=str(exc) or type(exc).__name__,
            source=self._source_from_exception(exception_block),
            environment=self.scope.static.environment,
            release=self.scope.static.release,
            trace_id=trace_id or self.scope.current_trace_id(),
            commit_hash=self.commit_hash,
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

        if self.scope.current_request() is not None:
            from datetime import datetime, timezone

            self.scope.add_request_log(
                level=level,
                message=message,
                source=source or caller_source(skip=2),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            return self.scope.current_trace_id()

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
            commit_hash=self.commit_hash,
            payload=payload,
            tags=tags,
            extra=extra,
        )
        return self._dispatch(envelope)

    def capture_log(
        self,
        message: str,
        *,
        level: str = "info",
        tags: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        """Record a structured log line (`kind=log`). Alias ergonomics over `capture_message`."""
        return self.capture_message(
            message,
            level=level,
            tags=tags,
            extra=extra,
            source=source,
            trace_id=trace_id,
            kind="log",
        )

    def capture_request(
        self,
        *,
        duration_ms: float,
        op: str,
        status_code: Optional[int] = None,
        method: Optional[str] = None,
        trace_id: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Emit one HTTP request footprint to the beam endpoint."""
        if not isinstance(duration_ms, (int, float)) or duration_ms < 0:
            debug(f"capture_request expects duration_ms >= 0, got {duration_ms!r}")
            return None
        if not isinstance(op, str) or not op.strip():
            debug("capture_request expects non-empty op str")
            return None
        code = status_code if status_code is not None else 200
        if not isinstance(code, int) or not (100 <= code <= 599):
            debug(f"capture_request invalid status_code: {status_code!r}")
            return None

        exception_block = self.scope.current_pending_exception()
        request_ctx = self.scope.current_request() or {}
        logs = self.scope.current_request_logs()
        headers = request_ctx.get("headers") if isinstance(request_ctx.get("headers"), dict) else {}

        footprint = build_footprint_payload(
            request_id=trace_id or self.scope.current_trace_id(),
            request_path=op.strip(),
            request_method=method,
            request_user=str(request_ctx.get("user") or "anonymous"),
            request_body=request_ctx.get("body"),
            response_time=float(duration_ms),
            status_code=code,
            system_logs=logs or None,
            ip_address=request_ctx.get("ip") or request_ctx.get("ip_address") or headers.get("x-forwarded-for"),
            user_agent=request_ctx.get("user_agent") or headers.get("user-agent"),
            exception_block=exception_block,
            environment=self.scope.static.environment,
            release=self.scope.static.release,
            commit_hash=self.commit_hash,
        )
        if tags:
            footprint["_tags"] = tags
        if extra:
            footprint["_extra"] = extra
        return self._dispatch_footprint(footprint)

    def capture_perf(
        self,
        op: str,
        duration_ms: float,
        *,
        status_code: Optional[int] = None,
        method: Optional[str] = None,
        level: str = "info",
        tags: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
        source: str = "django.request",
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Record a performance timing beacon (`kind=perf`).

        Used for HTTP request durations, slow queries, and other timing
        signals. Does not create Issues on the server — perf rows live in
        Beacons only. Pair with `trace_id` to link a perf row to an error
        on the same request (see DjangoIntegration).
        """
        if not isinstance(op, str) or not op.strip():
            debug("capture_perf expects non-empty op str")
            return None
        if not isinstance(duration_ms, (int, float)) or duration_ms < 0:
            debug(f"capture_perf expects duration_ms >= 0, got {duration_ms!r}")
            return None
        if status_code is not None:
            if not isinstance(status_code, int) or not (100 <= status_code <= 599):
                debug(f"capture_perf invalid status_code: {status_code!r}")
                return None
        level = level if level in VALID_LEVELS else "info"

        payload: Dict[str, Any] = {
            "runtime": runtime_payload(__version__),
            "duration_ms": float(duration_ms),
            "op": op.strip(),
        }
        if status_code is not None:
            payload["status_code"] = status_code
        if method is not None:
            payload["method"] = method

        request_ctx = self.scope.current_request()
        if request_ctx is not None:
            payload["request"] = request_ctx

        message = self._perf_summary_message(
            method=method,
            op=op.strip(),
            status_code=status_code,
            duration_ms=float(duration_ms),
        )

        envelope = build_envelope(
            kind="perf",
            level=level,
            message=message,
            source=source,
            environment=self.scope.static.environment,
            release=self.scope.static.release,
            trace_id=trace_id or self.scope.current_trace_id(),
            commit_hash=self.commit_hash,
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

    def _dispatch_footprint(self, footprint: Dict[str, Any]) -> Optional[str]:
        """Scrub → before_send → size budget → transport submit."""
        scrubbed = dict(footprint)
        scrubbed.pop("_tags", None)
        scrubbed.pop("_extra", None)
        if self.before_send is not None:
            try:
                wrapped = {"payload": scrubbed, **scrubbed}
                result = self.before_send(wrapped)  # type: ignore[assignment]
            except Exception as exc:
                debug(f"before_send raised {type(exc).__name__}: {exc}; dropping footprint")
                return None
            if result is None:
                return None
            if isinstance(result, dict) and "payload" in result:
                scrubbed = result["payload"]
            elif isinstance(result, dict):
                scrubbed = result

        if _byte_len_footprint(scrubbed) > MAX_ENVELOPE_BYTES:
            debug("footprint exceeds size budget; dropping")
            return None

        accepted = self.transport.submit(scrubbed)
        return scrubbed.get("request_id") if accepted else None

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

    @staticmethod
    def _perf_summary_message(
        *,
        method: Optional[str],
        op: str,
        status_code: Optional[int],
        duration_ms: float,
    ) -> str:
        """Short list-view label, e.g. `GET /api/users/ 200 45ms`."""
        parts: List[str] = []
        if method:
            parts.append(method)
        parts.append(op)
        if status_code is not None:
            parts.append(str(status_code))
        parts.append(f"{duration_ms:.0f}ms")
        return " ".join(parts)


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
    *,
    integrations: Optional[Sequence[IntegrationLike]] = None,
    **kwargs: Any,
) -> Optional[Client]:
    """
    Initialize the SDK. Returns the new `Client` on success, or `None`
    when no DSN is configured (disabled mode).

    Calling `init` a second time is allowed but logs a warning and
    closes the previous client first. The new client becomes the
    process-global one.

    Pass framework integrations via `integrations=[...]`. Each integration's
    `setup_once()` runs after the client is active.
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

    integration_list = list(integrations or [])

    with _init_lock:
        if _active_client is not None:
            debug("re-initializing; closing previous client")
            try:
                _active_client.close()
            except Exception as exc:
                debug(f"previous client close failed: {exc}")
        enable_logs = bool(kwargs.pop("enable_logs", False))
        client = Client(parsed, enable_logs=enable_logs, **kwargs)
        _set_active(client)

    _setup_integrations(integration_list)
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
def capture_log(
    message: str,
    *,
    level: str = "info",
    tags: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    source: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Optional[str]:
    client = _client()
    if client is None:
        return None
    return client.capture_log(
        message,
        level=level,
        tags=tags,
        extra=extra,
        source=source,
        trace_id=trace_id,
    )


@safe
def capture_request(
    *,
    duration_ms: float,
    op: str,
    status_code: Optional[int] = None,
    method: Optional[str] = None,
    trace_id: Optional[str] = None,
    tags: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    client = _client()
    if client is None:
        return None
    return client.capture_request(
        duration_ms=duration_ms,
        op=op,
        status_code=status_code,
        method=method,
        trace_id=trace_id,
        tags=tags,
        extra=extra,
    )


@safe
def capture_perf(
    op: str,
    duration_ms: float,
    *,
    status_code: Optional[int] = None,
    method: Optional[str] = None,
    level: str = "info",
    tags: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    source: str = "django.request",
    trace_id: Optional[str] = None,
) -> Optional[str]:
    client = _client()
    if client is None:
        return None
    return client.capture_perf(
        op,
        duration_ms,
        status_code=status_code,
        method=method,
        level=level,
        tags=tags,
        extra=extra,
        source=source,
        trace_id=trace_id,
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
