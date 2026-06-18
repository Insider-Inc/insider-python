"""Tests for capture_log — structured log beacons (C3c)."""

import insider
from insider.client import _set_active


def test_capture_log_records_envelope(sdk_client, fake_transport):
    insider.capture_log(
        "User signed in",
        level="info",
        tags={"user_id": "42"},
        extra={"ip": "127.0.0.1"},
        source="auth.views",
        trace_id="trace-log-1",
    )
    assert len(fake_transport.envelopes) == 1
    env = fake_transport.envelopes[0]
    assert env["kind"] == "log"
    assert env["level"] == "info"
    assert env["message"] == "User signed in"
    assert env["source"] == "auth.views"
    assert env["trace_id"] == "trace-log-1"
    assert env["payload"]["tags"] == {"user_id": "42"}
    assert env["payload"]["extra"] == {"ip": "127.0.0.1"}


def test_capture_log_defaults_to_info(sdk_client, fake_transport):
    insider.capture_log("hello")
    env = fake_transport.envelopes[0]
    assert env["kind"] == "log"
    assert env["level"] == "info"


def test_capture_log_rejects_non_string_message(sdk_client, fake_transport):
    assert insider.capture_log(123) is None  # type: ignore[arg-type]
    assert fake_transport.envelopes == []


def test_capture_without_init_is_noop():
    _set_active(None)
    assert insider.capture_log("hello") is None
