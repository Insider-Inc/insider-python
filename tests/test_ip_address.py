"""Tests for IP normalization on footprint ingest payloads."""

from __future__ import annotations

from insider._footprint import build_footprint_payload, normalize_ip_address


def test_normalize_ip_address_xff_list():
    assert (
        normalize_ip_address("203.0.113.10, 10.0.0.1, 10.0.0.2")
        == "203.0.113.10"
    )


def test_normalize_ip_address_single():
    assert normalize_ip_address("203.0.113.10") == "203.0.113.10"


def test_normalize_ip_address_ipv4_with_port():
    assert normalize_ip_address("203.0.113.10:54321") == "203.0.113.10"


def test_normalize_ip_address_ipv6_unchanged():
    assert normalize_ip_address("2001:db8::1") == "2001:db8::1"


def test_normalize_ip_address_empty():
    assert normalize_ip_address(None) is None
    assert normalize_ip_address("") is None
    assert normalize_ip_address("  , 10.0.0.1") == "10.0.0.1"


def test_footprint_payload_sanitizes_xff():
    fp = build_footprint_payload(
        request_id="abc",
        request_path="/currency/exchange-rate",
        request_method="GET",
        response_time=12.0,
        status_code=200,
        ip_address="198.51.100.7, 172.16.0.1",
    )
    assert fp["ip_address"] == "198.51.100.7"
    assert fp["request_method"] == "get"
