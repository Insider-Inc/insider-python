"""
Background HTTP transport.

The capture path is on the customer's request thread. Sending the beacon
on that thread would add a network round-trip to every error response —
that is exactly what we will not do. Instead:

  1. `submit(beacon)` puts the beacon on a bounded in-memory queue
     (`queue.Queue.put_nowait`).
  2. If the queue is full we drop the beacon and increment a counter.
     The customer's thread never blocks waiting on us.
  3. A daemon worker thread loops on `queue.get()` and POSTs each beacon
     to the beam endpoint. Any error during the POST is caught, logged,
     and the beacon discarded. No retries in v1 (see docs/python-sdk-plan
     -> Non-goals).
  4. `atexit` registers `close()` so short-lived scripts and management
     commands drain before exit (bounded by `flush_timeout`).

The transport is the *only* place inside the SDK that talks to the
network. Everything else is in-process work.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Dict, Optional

import urllib3

from ._version import __version__
from .dsn import DSN
from .safety import debug


_SENTINEL = object()


class BackgroundTransport:
    """
    Bounded queue + daemon worker thread + urllib3 connection pool.

    Public methods are thread-safe. `submit` is the only hot-path call.
    """

    def __init__(
        self,
        dsn: DSN,
        *,
        queue_size: int = 1000,
        flush_timeout: float = 2.0,
        connect_timeout: float = 2.0,
        read_timeout: float = 5.0,
    ) -> None:
        self._dsn = dsn
        self._flush_timeout = flush_timeout
        self._queue: "queue.Queue[Any]" = queue.Queue(maxsize=queue_size)
        self._pool: Optional[urllib3.PoolManager] = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=connect_timeout, read=read_timeout),
            retries=False,
            maxsize=4,
            block=False,
        )
        self._closed = threading.Event()

        # Bookkeeping the customer can read for telemetry-on-telemetry.
        self.submitted_total: int = 0
        self.sent_total: int = 0
        self.dropped_full: int = 0
        self.dropped_error: int = 0

        self._worker = threading.Thread(
            target=self._run,
            name="insider-transport",
            daemon=True,
        )
        self._worker.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(self, beacon: Dict[str, Any]) -> bool:
        """
        Enqueue a beacon. Returns True if accepted, False if dropped.
        Never blocks the caller. Never raises.
        """
        if self._closed.is_set():
            self.dropped_full += 1
            return False
        try:
            self._queue.put_nowait(beacon)
        except queue.Full:
            self.dropped_full += 1
            debug("queue full; dropping beacon")
            return False
        self.submitted_total += 1
        return True

    def flush(self, timeout: Optional[float] = None) -> bool:
        """
        Block until the queue drains or `timeout` elapses. Returns True
        if drained, False otherwise. `timeout=None` uses `flush_timeout`.
        """
        deadline = time.monotonic() + (
            timeout if timeout is not None else self._flush_timeout
        )
        while time.monotonic() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.01)
        return self._queue.unfinished_tasks == 0

    def close(self, timeout: Optional[float] = None) -> None:
        """
        Stop accepting new beacons, drain the queue, join the worker.
        Idempotent. Bounded by `timeout` (defaults to `flush_timeout`).
        """
        if self._closed.is_set():
            return
        self._closed.set()
        # Push sentinel even if queue is full — use put with timeout so we
        # don't hang shutdown forever if a runaway producer is filling it.
        try:
            self._queue.put(_SENTINEL, timeout=1.0)
        except queue.Full:
            debug("close: queue full, sentinel may be late")
        wait = timeout if timeout is not None else self._flush_timeout
        self._worker.join(timeout=wait)
        if self._pool is not None:
            try:
                self._pool.clear()
            except Exception as exc:
                debug(f"pool clear failed: {exc}")
            self._pool = None

    # ------------------------------------------------------------------
    # Worker loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        # Outer try guarantees the worker thread never dies on an unexpected
        # exception. Losing the worker would silently leak beacons forever.
        while True:
            try:
                item = self._queue.get()
            except Exception as exc:
                debug(f"queue.get failed: {exc}")
                continue

            try:
                if item is _SENTINEL:
                    return
                self._send_one(item)
            except Exception as exc:
                self.dropped_error += 1
                debug(f"send loop swallowed {type(exc).__name__}: {exc}")
            finally:
                try:
                    self._queue.task_done()
                except Exception:
                    pass

    def _send_one(self, beacon: Dict[str, Any]) -> None:
        if self._pool is None:
            self.dropped_error += 1
            return
        try:
            body = json.dumps(beacon, default=str, ensure_ascii=False).encode("utf-8")
        except Exception as exc:
            # If we can't even serialize, ship a minimal fallback so the
            # event isn't lost entirely.
            self.dropped_error += 1
            debug(f"json encode failed: {exc}; shipping minimal envelope")
            body = json.dumps(
                {
                    "kind": "error",
                    "level": "error",
                    "occurred_at": beacon.get("occurred_at"),
                    "message": "<beacon could not be serialized>",
                    "payload": {"truncated": True, "encode_error": str(exc)},
                },
                default=str,
            ).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._dsn.token}",
            "User-Agent": f"insider-python/{__version__}",
            "X-Insider-SDK": f"python/{__version__}",
        }

        try:
            resp = self._pool.urlopen(
                "POST",
                self._dsn.beam_url,
                body=body,
                headers=headers,
                retries=False,
                preload_content=True,
            )
        except Exception as exc:
            self.dropped_error += 1
            debug(f"POST failed: {type(exc).__name__}: {exc}")
            return

        if resp.status == 202:
            self.sent_total += 1
        else:
            self.dropped_error += 1
            debug(f"server returned {resp.status}; dropping beacon")
