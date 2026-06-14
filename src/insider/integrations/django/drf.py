"""
Optional DRF patch: link DRF Request objects for accurate body reads.
"""

from __future__ import annotations

from typing import Any

from ...safety import debug, safe
from .request import attach_drf_request_backref

_patched = False


def install() -> None:
    global _patched
    if _patched:
        return
    try:
        from rest_framework.views import APIView
    except ImportError:
        return

    old_initial = APIView.initial

    @safe
    def patched_initial(
        self: Any,
        request: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        try:
            attach_drf_request_backref(request._request, request)
        except Exception as exc:
            debug(f"drf initial backref failed: {exc}")
        return old_initial(self, request, *args, **kwargs)

    APIView.initial = patched_initial  # type: ignore[method-assign]
    _patched = True
