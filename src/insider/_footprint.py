"""Build flat footprint payloads for beam ingest."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._version import __version__
from .stacktrace import runtime_payload


def build_footprint_payload(
    *,
    request_id: Optional[str],
    request_path: str,
    request_method: Optional[str],
    request_user: str = "anonymous",
    request_body: Any = None,
    response_body: Any = None,
    response_time: float,
    status_code: int,
    system_logs: Optional[list] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    db_query_count: int = 0,
    exception_block: Optional[Dict[str, Any]] = None,
    environment: str = "production",
    release: Optional[str] = None,
    service_name: Optional[str] = None,
    commit_hash: Optional[str] = None,
) -> Dict[str, Any]:
    runtime = runtime_payload(__version__)
    stack_trace = None
    exception_name = None
    if exception_block:
        exception_name = exception_block.get("type")
        stack_trace = dict(exception_block)
        if commit_hash:
            stack_trace["commit_hash"] = commit_hash

    body = request_body
    if body is not None and not isinstance(body, (dict, list, str, int, float, bool)):
        body = str(body)

    return {
        "request_id": request_id,
        "request_user": request_user,
        "request_path": request_path,
        "request_body": body if body is not None else None,
        "request_method": (request_method or "").lower() or None,
        "response_body": response_body,
        "response_time": float(response_time),
        "status_code": status_code,
        "system_logs": system_logs,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "db_query_count": db_query_count,
        "exception_name": exception_name,
        "stack_trace": stack_trace,
        "service_name": service_name,
        "environment": environment,
        "language": runtime.get("language"),
        "framework": runtime.get("framework"),
        "release": release,
    }
