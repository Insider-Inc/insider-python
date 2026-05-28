"""
The "world on fire" suite.

Every public function of the SDK must return normally — not raise into
the host application — even when:

  * the DSN is missing or malformed
  * the network is down (we simulate by injecting a pool that always
    raises in `urlopen`)
  * the server returns garbage
  * `before_send` raises
  * the beacon contains a non-JSON-serializable / circular object
  * we throw obviously-wrong inputs at the public functions

If any of these tests fails, the SDK's core promise is broken.
"""

from __future__ import annotations

import insider
from insider.client import Client, _set_active
from insider.dsn import DSN


VALID = "https://t@insider.test/123e4567-e89b-12d3-a456-426614174000"


# ---------------------------------------------------------------------------
# Public surface, no sdk_client
# ---------------------------------------------------------------------------


def test_capture_with_no_client_returns_none():
    _set_active(None)
    assert insider.capture_message("hi") is None
    assert insider.capture_exception(ValueError("x")) is None
    assert insider.flush(0.1) is True
    insider.close(0.1)


def test_init_with_invalid_dsn_returns_none(monkeypatch):
    monkeypatch.delenv("INSIDER_DSN", raising=False)
    assert insider.init("not a dsn") is None
    assert insider.init("ftp://t@h/123e4567-e89b-12d3-a456-426614174000") is None


def test_init_with_empty_env_var_returns_none(monkeypatch):
    monkeypatch.setenv("INSIDER_DSN", "")
    assert insider.init() is None


# ---------------------------------------------------------------------------
# Bad inputs to public functions
# ---------------------------------------------------------------------------


def test_capture_message_non_string(sdk_client):
    assert insider.capture_message(12345) is None  # type: ignore[arg-type]
    assert insider.capture_message(None) is None  # type: ignore[arg-type]


def test_capture_exception_non_exception(sdk_client):
    assert insider.capture_exception("not an exception") is None  # type: ignore[arg-type]
    assert insider.capture_exception(None) is None  # type: ignore[arg-type]


def test_capture_exception_invalid_level_falls_back(sdk_client, fake_transport):
    try:
        raise ValueError("x")
    except ValueError as exc:
        insider.capture_exception(exc, level="not-a-real-level")
    assert fake_transport.envelopes[0]["level"] == "error"


# ---------------------------------------------------------------------------
# Hostile data shapes
# ---------------------------------------------------------------------------


def test_non_serializable_extra_does_not_crash(sdk_client, fake_transport):
    class Weird:
        def __repr__(self):
            return "<weird>"

    insider.capture_message("ping", extra={"obj": Weird()})
    assert len(fake_transport.envelopes) == 1


def test_circular_reference_in_extra(sdk_client, fake_transport):
    a = {}
    a["self"] = a
    # The capture itself must not raise. The fake transport just records,
    # so we just verify we got *something* and the host stayed alive.
    insider.capture_message("loop", extra=a)
    assert len(fake_transport.envelopes) == 1


# ---------------------------------------------------------------------------
# Network failure
# ---------------------------------------------------------------------------


def test_pool_raising_does_not_crash():
    class ExplodingPool:
        def urlopen(self, *a, **kw):
            raise OSError("network down")

        def clear(self):
            pass

    from insider.transport import BackgroundTransport

    transport = BackgroundTransport(DSN.parse(VALID), queue_size=10)
    transport._pool = ExplodingPool()  # type: ignore[assignment]
    sdk_client = Client(DSN.parse(VALID), transport=transport)  # type: ignore[arg-type]
    _set_active(sdk_client)
    insider.capture_message("ping")
    assert transport.flush(timeout=2.0)
    transport.close(timeout=1.0)
    assert transport.dropped_error >= 1


# ---------------------------------------------------------------------------
# Hooks behaving badly
# ---------------------------------------------------------------------------


def test_before_send_raising(sdk_client, fake_transport):
    sdk_client.before_send = lambda env: (_ for _ in ()).throw(RuntimeError("nope"))
    insider.capture_message("ping")
    assert fake_transport.envelopes == []  # dropped, not crashed


def test_before_send_returning_garbage(sdk_client, fake_transport):
    sdk_client.before_send = lambda env: 42  # not a dict
    # The transport will choke on a non-dict, but the public function still
    # returns without raising.
    insider.capture_message("ping")
