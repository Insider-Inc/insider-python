"""
Stack frame extraction.

Given an exception (and therefore a traceback), produce a serializable
list of frames the dashboard can render. We deliberately *don't* read
source files in v1 — that's I/O on the error path and a chunk of
deferred work (see docs/python-sdk-plan -> Non-goals). We also don't
capture frame-local variables (security risk, opt-in feature later).

`in_app` is a hint to the dashboard about which frames are "the
customer's code" vs library / stdlib code. Default heuristic:

    in_app == filename does not live under site-packages / dist-packages
              and is not under the stdlib path

The customer can override with `in_app_include=["/srv/myapp", ...]`,
which switches to an explicit allow-list.
"""

from __future__ import annotations

import os
import sys
from types import TracebackType
from typing import Any, Dict, Iterable, List, Optional

from .safety import debug

# Computed once at import time. Falls back to "" if `os.__file__` isn't a
# usable path (e.g. frozen Python build).
_STDLIB_PATH = os.path.dirname(getattr(os, "__file__", "") or "")


def is_in_app(
    filename: Optional[str],
    in_app_include: Optional[Iterable[str]] = None,
) -> bool:
    """Return True if `filename` should be flagged as customer code."""
    if not filename or filename.startswith("<"):
        return False
    if in_app_include:
        return any(filename.startswith(prefix) for prefix in in_app_include)
    if "site-packages" in filename or "dist-packages" in filename:
        return False
    if _STDLIB_PATH and filename.startswith(_STDLIB_PATH):
        return False
    return True


def extract_frames(
    tb: Optional[TracebackType],
    *,
    in_app_include: Optional[Iterable[str]] = None,
    max_frames: int = 200,
) -> List[Dict[str, Any]]:
    """
    Walk a traceback into a list of frame dicts.

    Order: innermost (where the exception was raised) is last, matching
    Python's own `traceback` module. The dashboard renders top-down.
    `max_frames` is a guardrail against pathological recursion.
    """
    frames: List[Dict[str, Any]] = []
    walked = 0
    while tb is not None and walked < max_frames:
        try:
            frame = tb.tb_frame
            code = frame.f_code
            filename = code.co_filename
            frames.append(
                {
                    "filename": filename,
                    "function": code.co_name,
                    "module": frame.f_globals.get("__name__", ""),
                    "lineno": tb.tb_lineno,
                    "in_app": is_in_app(filename, in_app_include),
                }
            )
        except Exception as exc:
            debug(f"frame extraction skipped one frame: {exc}")
        tb = tb.tb_next
        walked += 1
    return frames


def exception_payload(
    exc: BaseException,
    *,
    in_app_include: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """
    Build the `payload.exception` block.

    Walks `__cause__` / `__context__` and stops at a small chain depth so
    we don't accidentally serialize a circular chain forever.
    """
    chain: List[Dict[str, Any]] = []
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    while current is not None and len(chain) < 10 and id(current) not in seen:
        seen.add(id(current))
        chain.append(
            {
                "type": type(current).__name__,
                "module": type(current).__module__,
                "value": str(current),
                "frames": extract_frames(
                    current.__traceback__,
                    in_app_include=in_app_include,
                ),
            }
        )
        current = current.__cause__ or current.__context__

    head = chain[0]
    if len(chain) > 1:
        head["chain"] = chain[1:]
    return head


def runtime_payload(sdk_version: str) -> Dict[str, Any]:
    """Static runtime info to attach to every error envelope."""
    return {
        "sdk": "insider-python",
        "sdk_version": sdk_version,
        "python_version": (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ),
        "platform": sys.platform,
    }


def caller_source(skip: int = 1) -> Optional[str]:
    """
    Return `<module>.<function>` of the first non-SDK caller above this
    function. `skip` is the minimum number of frames to skip before we
    start looking for a non-internal frame.

    We walk frames because the `@safe` decorator and the module-level
    facade each add a stack frame on top of `Client.capture_message`;
    a fixed `skip` would be brittle.
    """
    try:
        frame = sys._getframe(skip)
        while frame is not None:
            module = frame.f_globals.get("__name__", "") or ""
            if not module.startswith("insider"):
                function = frame.f_code.co_name
                return f"{module}.{function}" if module else function
            frame = frame.f_back
        return None
    except Exception:
        return None
