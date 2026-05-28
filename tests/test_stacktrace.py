import os

from insider.stacktrace import (
    caller_source,
    exception_payload,
    extract_frames,
    is_in_app,
    runtime_payload,
)


def test_is_in_app_skips_stdlib():
    assert is_in_app(os.__file__) is False


def test_is_in_app_skips_site_packages():
    assert is_in_app("/foo/site-packages/bar.py") is False
    assert is_in_app("/foo/dist-packages/bar.py") is False


def test_is_in_app_skips_synthetic_filenames():
    assert is_in_app("<string>") is False
    assert is_in_app("") is False
    assert is_in_app(None) is False


def test_is_in_app_explicit_allowlist():
    assert is_in_app("/srv/myapp/views.py", ["/srv/myapp"]) is True
    assert is_in_app("/srv/other/views.py", ["/srv/myapp"]) is False


def test_extract_frames_orders_innermost_last():
    def inner():
        raise ValueError("boom")

    def outer():
        inner()

    try:
        outer()
    except ValueError as exc:
        frames = extract_frames(exc.__traceback__)

    assert len(frames) >= 2
    assert frames[-1]["function"] == "inner"
    assert frames[-2]["function"] == "outer"
    assert frames[-1]["lineno"] > 0


def test_extract_frames_max_cap():
    def recurse(n):
        if n == 0:
            raise ValueError("bottom")
        recurse(n - 1)

    try:
        recurse(50)
    except ValueError as exc:
        frames = extract_frames(exc.__traceback__, max_frames=10)

    assert len(frames) == 10


def test_exception_payload_walks_cause_chain():
    def lower():
        raise ValueError("low")

    def upper():
        try:
            lower()
        except ValueError as exc:
            raise RuntimeError("high") from exc

    try:
        upper()
    except RuntimeError as exc:
        block = exception_payload(exc)

    assert block["type"] == "RuntimeError"
    assert block["value"] == "high"
    assert "chain" in block
    assert block["chain"][0]["type"] == "ValueError"


def test_runtime_payload_has_sdk_version():
    rt = runtime_payload("0.1.0")
    assert rt["sdk"] == "insider-python"
    assert rt["sdk_version"] == "0.1.0"
    assert "python_version" in rt
    assert "platform" in rt


def test_caller_source_returns_module_function():
    def fn():
        return caller_source(skip=1)

    out = fn()
    assert out is not None
    assert ".fn" in out
