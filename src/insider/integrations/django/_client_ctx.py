"""Build request context kwargs from the active SDK client."""

from __future__ import annotations

from typing import Any, Dict

from ...client import _client


def request_ctx_kwargs() -> Dict[str, Any]:
    client = _client()
    if client is None:
        return {}
    return {
        "header_policy": client.header_policy,
        "header_scrub_names": client.header_scrub_names,
        "scrub_defaults": client.scrub_defaults,
    }
