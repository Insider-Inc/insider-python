"""Tests for path ignore rules and client privacy options."""

from __future__ import annotations

import insider
from insider.client import Client
from insider.dsn import DSN
from insider.paths import path_is_ignored
from insider.scrubbing import FILTERED
from tests.conftest import VALID_DSN, FakeTransport


def test_path_is_ignored_prefix_match():
    assert path_is_ignored("/static/app.js", ["/static/"])
    assert path_is_ignored("/health", ["/health"])
    assert not path_is_ignored("/api/users", ["/static/"])


def test_scrub_defaults_false_leaves_builtin_keys(sdk_client):
    sdk_client.scrub_defaults = False
    sdk_client.scrub_keys = []
    out = sdk_client._scrub_data({"password": "secret"})
    assert out["password"] == "secret"


def test_scrub_defaults_true_masks_payload(sdk_client):
    sdk_client.scrub_defaults = True
    out = sdk_client._scrub_data({"password": "secret"})
    assert out["password"] == FILTERED


def test_scrub_defaults_true_masks_footprint_json_body(sdk_client, fake_transport):
    sdk_client.scrub_defaults = True
    sdk_client.scope.set_request({"body": '{"password": "x", "note": "ok"}'})
    sdk_client.capture_request(
        duration_ms=1.0,
        op="/login/",
        method="POST",
        trace_id="abc",
    )
    fp = fake_transport.envelopes[0]
    assert fp["request_body"]["password"] == FILTERED
    assert fp["request_body"]["note"] == "ok"


def test_ignore_paths_skips_capture(sdk_client, fake_transport):
    sdk_client.add_ignore_paths(["/noise/"])
    assert sdk_client.path_is_ignored("/noise/ping")
    sdk_client.capture_request(duration_ms=1.0, op="/noise/ping", trace_id="t1")
    assert fake_transport.envelopes == []


def test_scrub_dict_overrides_top_level():
    transport = FakeTransport()
    client = Client(
        DSN.parse(VALID_DSN),
        scrub_defaults=False,
        scrub_keys=["keep_me"],
        scrub={"defaults": True, "body_keys": ["custom"]},
        transport=transport,  # type: ignore[arg-type]
    )
    client.scope.set_request({"custom": "v", "keep_me": "v"})
    client.capture_perf("/x", 1.0)
    request = transport.envelopes[0]["payload"]["request"]
    assert request["custom"] == FILTERED
    assert request["keep_me"] == "v"


def test_init_warns_when_pii_without_scrub(monkeypatch):
    warnings: list[str] = []

    def _capture(msg: str) -> None:
        warnings.append(msg)

    monkeypatch.setattr(insider.client, "debug", _capture)
    insider.client._pii_warning_emitted = False
    transport = FakeTransport()
    Client(
        DSN.parse(VALID_DSN),
        send_default_pii=True,
        transport=transport,  # type: ignore[arg-type]
    )
    assert any("send_default_pii=True" in w for w in warnings)


def test_ignore_builtin_paths_disabled():
    client = Client(
        DSN.parse(VALID_DSN),
        ignore_builtin_paths=False,
        transport=FakeTransport(),  # type: ignore[arg-type]
    )
    assert not client.path_is_ignored("/static/app.js")
    assert client.path_is_ignored("/static/app.js") is False


def test_init_warns_on_invalid_header_policy(monkeypatch):
    warnings: list[str] = []

    def _capture(msg: str) -> None:
        warnings.append(msg)

    monkeypatch.setattr(insider.privacy, "debug", _capture)
    Client(
        DSN.parse(VALID_DSN),
        header_policy="allow_list",
        transport=FakeTransport(),  # type: ignore[arg-type]
    )
    assert any("unknown header_policy" in w for w in warnings)


def test_init_warns_header_all_without_scrub(monkeypatch):
    warnings: list[str] = []

    def _capture(msg: str) -> None:
        warnings.append(msg)

    monkeypatch.setattr(insider.client, "debug", _capture)
    insider.client._header_all_warning_emitted = False
    Client(
        DSN.parse(VALID_DSN),
        header_policy="all",
        transport=FakeTransport(),  # type: ignore[arg-type]
    )
    assert any("header_policy='all'" in w for w in warnings)


def test_init_warns_logs_without_scrub(monkeypatch):
    warnings: list[str] = []

    def _capture(msg: str) -> None:
        warnings.append(msg)

    monkeypatch.setattr(insider.client, "debug", _capture)
    insider.client._logs_warning_emitted = False
    Client(
        DSN.parse(VALID_DSN),
        enable_logs=True,
        transport=FakeTransport(),  # type: ignore[arg-type]
    )
    assert any("enable_logs=True" in w for w in warnings)
