"""Helpers for exercising ASGI applications in tests (Daphne/uvicorn path)."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple


async def request_asgi(
    app: Any,
    path: str,
    *,
    method: str = "GET",
    headers: Optional[List[Tuple[bytes, bytes]]] = None,
) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Drive a raw ASGI HTTP app the same way Daphne/uvicorn would.

    Django's ``AsyncClient`` uses ``AsyncClientHandler`` internally and does
    not invoke a custom ``application`` callable — use this for
    ``wrap_asgi_application()`` tests.
    """
    messages: List[Dict[str, Any]] = []
    body_delivered = False

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": headers
        if headers is not None
        else [(b"host", b"testserver"), (b"user-agent", b"insider-asgi-test")],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }

    async def receive() -> Dict[str, Any]:
        nonlocal body_delivered
        if not body_delivered:
            body_delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        # Django's listen_for_disconnect() waits for http.disconnect. Real
        # servers only send that after the response; block so tests do not
        # abort the in-flight request task.
        await asyncio.get_running_loop().create_future()
        return {"type": "http.disconnect"}  # pragma: no cover

    async def send(message: Dict[str, Any]) -> None:
        messages.append(message)

    await app(scope, receive, send)
    status = 500
    for message in messages:
        if message.get("type") == "http.response.start":
            status = int(message.get("status", 500))
    return status, messages


def run_asgi(app: Any, path: str, **kwargs: Any) -> Tuple[int, List[Dict[str, Any]]]:
    return asyncio.run(request_asgi(app, path, **kwargs))
