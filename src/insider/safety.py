"""
The never-crash machinery.

Every public entrypoint of the SDK is wrapped with `@safe`, which catches
any `Exception` raised by the wrapped function and routes it through the
SDK's debug logger. The host application sees `None` instead of an
exception. That is the contract: the SDK cannot crash the customer's app.

Why `print` to stderr instead of the `logging` module?
    The SDK may be initialized *before* the customer's logging config is
    in place. Using the stdlib `logging` module risks recursing into a
    customer LoggingHandler that itself uses Insider (phase 4 of the
    plan). Writing directly to stderr is dependency-free and recursion-free.
"""

from __future__ import annotations

import functools
import sys
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

_debug_enabled: bool = False


def set_debug(enabled: bool) -> None:
    """Toggle SDK-internal debug logging. Called from `Client.__init__`."""
    global _debug_enabled
    _debug_enabled = bool(enabled)


def debug(message: str) -> None:
    """Write a single line to stderr if debug mode is on. Never raises."""
    if not _debug_enabled:
        return
    try:
        sys.stderr.write(f"[insider] {message}\n")
    except Exception:
        pass


def safe(fn: F) -> F:
    """
    Decorator: swallow every exception raised by `fn`, return `None`
    instead, and emit a debug line. The original return value is passed
    through on success.

    Use on every public entrypoint. Internal helpers can raise normally;
    the boundary functions catch them.
    """

    if asyncio_iscoroutinefunction(fn):
        return safe_async(fn)  # type: ignore[return-value]

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            debug(f"swallowed {type(exc).__name__} in {fn.__qualname__}: {exc}")
            return None

    return wrapper  # type: ignore[return-value]


def asyncio_iscoroutinefunction(fn: Any) -> bool:
    try:
        import asyncio

        return asyncio.iscoroutinefunction(fn)
    except Exception:
        return False


def safe_async(fn: F) -> F:
    """Like `@safe` for async functions — preserves the coroutine contract."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:
            debug(f"swallowed {type(exc).__name__} in {fn.__qualname__}: {exc}")
            return None

    return wrapper  # type: ignore[return-value]
