"""Shared pytest fixtures."""

from __future__ import annotations

import threading
from typing import Any, Dict, List

import pytest

import insider
from insider.client import Client, _set_active
from insider.dsn import DSN


VALID_DSN = "https://abc-token@insider.test/123e4567-e89b-12d3-a456-426614174000"


class FakeTransport:
    """In-memory transport. Records every submitted envelope, never sends."""

    def __init__(self) -> None:
        self.envelopes: List[Dict[str, Any]] = []
        self.submitted_total = 0
        self.sent_total = 0
        self.dropped_full = 0
        self.dropped_error = 0
        self._lock = threading.Lock()

    def submit(self, beacon: Dict[str, Any]) -> bool:
        with self._lock:
            self.envelopes.append(beacon)
            self.submitted_total += 1
            self.sent_total += 1
        return True

    def flush(self, timeout: float | None = None) -> bool:
        return True

    def close(self, timeout: float | None = None) -> None:
        return None


@pytest.fixture(autouse=True)
def _isolate_active_client():
    """Tear down any process-global client after each test."""
    yield
    _set_active(None)


@pytest.fixture
def fake_transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def sdk_client(fake_transport: FakeTransport) -> Client:
    """A `Client` configured with a fake transport. Hooked up as the active client.

    Named `sdk_client` (not `client`) so it doesn't shadow pytest-django's
    `client` fixture (the Django test client).
    """
    c = Client(
        DSN.parse(VALID_DSN),
        environment="test",
        release="0.0.0-test",
        transport=fake_transport,  # type: ignore[arg-type]
    )
    _set_active(c)
    return c
