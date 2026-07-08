"""Test middleware that assigns ``request.user`` inside the Django request cycle."""

from __future__ import annotations

from typing import Any, Optional

deferred_user: Optional[Any] = None


class DeferredUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if deferred_user is not None:
            request.user = deferred_user
        return self.get_response(request)
