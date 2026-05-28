"""Real transport tests using a fake urllib3 PoolManager."""

from __future__ import annotations

import threading
import time
from typing import Any, List

from insider.dsn import DSN
from insider.transport import BackgroundTransport


VALID = "https://t@insider.test/123e4567-e89b-12d3-a456-426614174000"


class _Recorder:
    """Stand-in for urllib3.PoolManager — records calls and replays a response."""

    def __init__(self, status: int = 202) -> None:
        self.status = status
        self.calls: List[Any] = []
        self.cleared = False
        self._lock = threading.Lock()

    def urlopen(self, method, url, body=None, headers=None, **kwargs):  # noqa: D401
        with self._lock:
            self.calls.append({"method": method, "url": url, "body": body, "headers": headers})

        class FakeResponse:
            pass

        resp = FakeResponse()
        resp.status = self.status
        return resp

    def clear(self):
        self.cleared = True


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_submit_and_send():
    dsn = DSN.parse(VALID)
    transport = BackgroundTransport(dsn, queue_size=10)
    recorder = _Recorder(status=202)
    transport._pool = recorder  # type: ignore[assignment]

    assert transport.submit({"kind": "log", "message": "hi"})
    assert transport.flush(timeout=2.0)
    transport.close(timeout=2.0)

    assert recorder.calls, "expected one POST"
    call = recorder.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/api/v1/beam/123e4567-e89b-12d3-a456-426614174000/")
    assert call["headers"]["Authorization"] == "Bearer t"
    assert call["headers"]["User-Agent"].startswith("insider-python/")
    assert b'"kind": "log"' in call["body"] or b'"kind":"log"' in call["body"]
    assert transport.sent_total == 1


def test_drops_when_queue_full():
    dsn = DSN.parse(VALID)
    transport = BackgroundTransport(dsn, queue_size=1)
    # Block the worker by replacing the pool with one that sleeps.
    block = threading.Event()

    class BlockingPool:
        def urlopen(self, *a, **kw):
            block.wait(timeout=1.0)

            class R:
                status = 202

            return R()

        def clear(self):
            pass

    transport._pool = BlockingPool()  # type: ignore[assignment]
    # Fill the queue: one in flight, one queued, third should drop.
    assert transport.submit({"a": 1}) is True
    # Give the worker a tick to dequeue
    time.sleep(0.05)
    transport.submit({"a": 2})
    dropped = transport.submit({"a": 3})
    assert dropped is False or transport.dropped_full >= 1
    block.set()
    transport.close(timeout=2.0)


def test_non_202_counts_as_dropped():
    dsn = DSN.parse(VALID)
    transport = BackgroundTransport(dsn, queue_size=10)
    transport._pool = _Recorder(status=500)  # type: ignore[assignment]
    transport.submit({"a": 1})
    transport.flush(timeout=2.0)
    transport.close(timeout=2.0)
    assert transport.dropped_error == 1
    assert transport.sent_total == 0


def test_close_is_idempotent():
    dsn = DSN.parse(VALID)
    transport = BackgroundTransport(dsn, queue_size=10)
    transport._pool = _Recorder()  # type: ignore[assignment]
    transport.close(timeout=1.0)
    transport.close(timeout=1.0)
    transport.close(timeout=1.0)


def test_submit_after_close_is_dropped():
    dsn = DSN.parse(VALID)
    transport = BackgroundTransport(dsn, queue_size=10)
    transport._pool = _Recorder()  # type: ignore[assignment]
    transport.close(timeout=1.0)
    assert transport.submit({"a": 1}) is False
