"""Tests for LoggingIntegration — stdlib logging → request-scoped system_logs."""

from __future__ import annotations

import logging

import pytest

from insider.integrations.logging import LoggingIntegration


@pytest.fixture(autouse=True)
def _install_logging_integration():
    LoggingIntegration().setup_once()
    yield


def test_logging_embeds_in_request_footprint(sdk_client, fake_transport):
    sdk_client.enable_logs = True
    sdk_client.scope.set_request({"path": "/ok/", "method": "GET"})
    log = logging.getLogger("tests.app")
    log.setLevel(logging.INFO)
    log.info("hello from logging")

    sdk_client.capture_request(duration_ms=1.0, op="/ok/", status_code=200)

    assert len(fake_transport.envelopes) == 1
    logs = fake_transport.envelopes[0].get("system_logs") or []
    assert any(line.get("message") == "hello from logging" for line in logs)


def test_logging_error_level_in_request(sdk_client, fake_transport):
    sdk_client.enable_logs = True
    sdk_client.scope.set_request({"path": "/ok/", "method": "GET"})
    log = logging.getLogger("tests.app")
    log.setLevel(logging.ERROR)
    log.error("something broke")

    sdk_client.capture_request(duration_ms=1.0, op="/ok/", status_code=200)

    logs = fake_transport.envelopes[0].get("system_logs") or []
    assert logs[-1]["level"] == "error"


def test_enable_logs_false_skips_beacon_but_keeps_breadcrumb(sdk_client, fake_transport):
    from insider.integrations.logging import LoggingIntegration

    LoggingIntegration().setup_once()
    sdk_client.enable_logs = False
    log = logging.getLogger("tests.breadcrumb")
    log.setLevel(logging.WARNING)
    log.warning("breadcrumb only")

    assert fake_transport.envelopes == []
    crumbs = sdk_client.scope.current_breadcrumbs()
    assert len(crumbs) == 1
    assert crumbs[0]["message"] == "breadcrumb only"
    assert crumbs[0]["level"] == "warning"


def test_breadcrumbs_persist_until_request_cycle_cleared(sdk_client, fake_transport):
    sdk_client.enable_logs = False
    logging.getLogger("tests.app").info("before crash")
    sdk_client.scope.set_pending_exception(
        {"type": "ValueError", "value": "boom", "frames": []}
    )
    sdk_client.capture_request(duration_ms=1.0, op="/boom/", status_code=500)

    fp = fake_transport.envelopes[0]
    assert fp.get("exception_name") == "ValueError"


def test_respects_logger_level(sdk_client, fake_transport):
    sdk_client.enable_logs = True
    quiet = logging.getLogger("tests.quiet")
    quiet.setLevel(logging.WARNING)
    quiet.info("should not appear")

    assert fake_transport.envelopes == []


def test_insider_logger_not_recursed(sdk_client, fake_transport):
    sdk_client.enable_logs = True
    logging.getLogger("insider.transport").info("internal")

    assert fake_transport.envelopes == []


def test_breadcrumb_ring_buffer_cap(sdk_client, fake_transport):
    sdk_client.enable_logs = False
    log = logging.getLogger("tests.spam")
    log.setLevel(logging.INFO)
    for i in range(60):
        log.info(f"line {i}")

    assert len(sdk_client.scope.current_breadcrumbs()) == 50
    assert sdk_client.scope.current_breadcrumbs()[0]["message"] == "line 10"
