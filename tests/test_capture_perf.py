"""Tests for capture_perf — lightweight HTTP timing beacons (C3a)."""

import insider
from insider.client import _set_active


def test_capture_perf_records_envelope(sdk_client, fake_transport):
    insider.capture_perf(
        op="/api/users/",
        duration_ms=45.2,
        status_code=200,
        method="GET",
        trace_id="trace-abc",
    )
    assert len(fake_transport.envelopes) == 1
    env = fake_transport.envelopes[0]
    assert env["kind"] == "perf"
    assert env["level"] == "info"
    assert env["source"] == "django.request"
    assert env["trace_id"] == "trace-abc"
    assert "GET" in env["message"]
    assert "/api/users/" in env["message"]
    assert "200" in env["message"]
    assert env["payload"]["duration_ms"] == 45.2
    assert env["payload"]["status_code"] == 200
    assert env["payload"]["method"] == "GET"
    assert env["payload"]["op"] == "/api/users/"


def test_capture_perf_custom_source(sdk_client, fake_transport):
    insider.capture_perf(
        op="celery.tasks.send_email",
        duration_ms=120,
        source="celery.task",
    )
    env = fake_transport.envelopes[0]
    assert env["source"] == "celery.task"
    assert env["payload"]["duration_ms"] == 120


def test_capture_perf_rejects_invalid_op(sdk_client, fake_transport):
    assert insider.capture_perf(op="", duration_ms=10) is None
    assert insider.capture_perf(op=123, duration_ms=10) is None  # type: ignore[arg-type]
    assert fake_transport.envelopes == []


def test_capture_perf_rejects_negative_duration(sdk_client, fake_transport):
    assert insider.capture_perf(op="/slow/", duration_ms=-1) is None
    assert fake_transport.envelopes == []


def test_capture_perf_rejects_invalid_status_code(sdk_client, fake_transport):
    assert insider.capture_perf(op="/x/", duration_ms=1, status_code=99) is None
    assert insider.capture_perf(op="/x/", duration_ms=1, status_code="200") is None  # type: ignore[arg-type]
    assert fake_transport.envelopes == []


def test_capture_without_init_is_noop():
    _set_active(None)
    assert insider.capture_perf(op="/x/", duration_ms=1) is None
