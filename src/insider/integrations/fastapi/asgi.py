"""
Patch ``Starlette.__call__`` so every FastAPI HTTP request emits one footprint.

FastAPI is a Starlette app. Patching the base ``__call__`` covers apps created
before or after ``FastAPIIntegration.setup_once()``, without asking the host
to add middleware.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from ...client import _client
from ...safety import debug
from ...stacktrace import exception_payload
from .request import build_request_ctx, user_payload_from_scope

_patched = False
_auto_perf = True

_MAX_REQUEST_BODY_BYTES = 32 * 1024
_MAX_RESPONSE_BODY_BYTES = 8 * 1024


def install(*, auto_perf: bool = True) -> None:
    global _patched, _auto_perf
    _auto_perf = auto_perf
    if _patched:
        return
    try:
        from starlette.applications import Starlette
    except ImportError:
        debug("FastAPIIntegration: starlette is not installed")
        return

    original = Starlette.__call__

    async def patched(self: Any, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await original(self, scope, receive, send)
            return

        client = _client()
        if client is None:
            await original(self, scope, receive, send)
            return

        path = scope.get("path") or "/"
        if client.path_is_ignored(path):
            await original(self, scope, receive, send)
            return

        trace_id = uuid.uuid4().hex
        try:
            client.scope.set_trace_id(trace_id)
            client.scope.set_request(
                build_request_ctx(
                    scope,
                    client.send_default_pii,
                    header_policy=client.header_policy,
                    header_scrub_names=client.header_scrub_names,
                    scrub_defaults=client.scrub_defaults,
                )
            )
        except Exception as exc:
            debug(f"FastAPIIntegration: scope setup failed: {exc}")

        start = time.perf_counter()
        status_code: Optional[int] = None
        request_chunks: List[bytes] = []
        response_chunks: List[bytes] = []
        streaming = False
        request_bytes = 0
        caught: Optional[BaseException] = None

        async def receive_wrapped() -> Dict[str, Any]:
            nonlocal request_bytes
            message = await receive()
            if (
                client.send_default_pii
                and message.get("type") == "http.request"
                and request_bytes < _MAX_REQUEST_BODY_BYTES
            ):
                chunk = message.get("body") or b""
                if chunk:
                    request_chunks.append(chunk)
                    request_bytes += len(chunk)
            return message

        async def send_wrapped(message: Dict[str, Any]) -> None:
            nonlocal status_code, streaming
            if message.get("type") == "http.response.start":
                status_code = message.get("status", status_code)
            elif (
                message.get("type") == "http.response.body"
                and client.send_default_pii
                and not streaming
            ):
                chunk = message.get("body") or b""
                if message.get("more_body") or (response_chunks and chunk):
                    streaming = True
                    response_chunks.clear()
                elif chunk:
                    response_chunks.append(chunk)
            await send(message)

        try:
            await original(self, scope, receive_wrapped, send_wrapped)
        except BaseException as exc:
            caught = exc
            raise
        finally:
            try:
                _finish_request(
                    scope,
                    start=start,
                    status_code=status_code,
                    trace_id=trace_id,
                    caught=caught,
                    request_chunks=request_chunks,
                    response_chunks=response_chunks,
                    streaming=streaming,
                )
            except Exception as exc:
                debug(f"FastAPIIntegration: footprint emit failed: {exc}")
                try:
                    if client is not None:
                        client.scope.clear_request_cycle()
                except Exception:
                    pass

    Starlette.__call__ = patched  # type: ignore[method-assign]
    _patched = True


def _finish_request(
    scope: Dict[str, Any],
    *,
    start: float,
    status_code: Optional[int],
    trace_id: str,
    caught: Optional[BaseException],
    request_chunks: List[bytes],
    response_chunks: List[bytes],
    streaming: bool,
) -> None:
    client = _client()
    if client is None:
        return
    try:
        if isinstance(caught, Exception):
            client.scope.set_pending_exception(
                exception_payload(
                    caught, in_app_include=client.scope.static.in_app_include
                )
            )
            if status_code is None:
                status_code = 500

        ctx = dict(client.scope.current_request() or {})
        if client.send_default_pii:
            user_payload = user_payload_from_scope(scope)
            if user_payload is not None:
                ctx["user"] = user_payload
            else:
                ctx.pop("user", None)
            body = _decode_body(request_chunks, _MAX_REQUEST_BODY_BYTES)
            if body is not None:
                ctx["body"] = body
            if not streaming:
                response_body = _decode_body(response_chunks, _MAX_RESPONSE_BODY_BYTES)
                if response_body is not None:
                    ctx["response_body"] = response_body
        client.scope.set_request(ctx)

        if _auto_perf:
            code = status_code if status_code is not None else 200
            client.capture_request(
                duration_ms=(time.perf_counter() - start) * 1000.0,
                op=scope.get("path") or "/",
                status_code=code,
                method=scope.get("method"),
                trace_id=trace_id,
                framework="fastapi",
                language="python",
            )
    finally:
        client.scope.clear_request_cycle()


def _decode_body(chunks: List[bytes], limit: int) -> Optional[str]:
    if not chunks:
        return None
    raw = b"".join(chunks)
    suffix = ""
    if len(raw) > limit:
        raw = raw[:limit]
        suffix = "...[truncated]"
    return raw.decode("utf-8", errors="replace") + suffix
