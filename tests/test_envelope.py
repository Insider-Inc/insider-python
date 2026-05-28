import json

from insider._envelope import (
    MAX_ENVELOPE_BYTES,
    build_envelope,
    enforce_size_budget,
)


def test_build_envelope_has_required_top_level():
    env = build_envelope(
        kind="error",
        level="error",
        message="boom",
        source="m.f",
        environment="prod",
        release="1.0",
        trace_id=None,
        payload={"exception": {"type": "X"}},
    )
    for key in (
        "kind",
        "level",
        "environment",
        "release",
        "source",
        "message",
        "occurred_at",
        "trace_id",
        "payload",
    ):
        assert key in env
    assert env["payload"]["exception"]["type"] == "X"


def test_message_truncated_at_8kb():
    env = build_envelope(
        kind="log",
        level="info",
        message="a" * (20 * 1024),
        source=None,
        environment="prod",
        release=None,
        trace_id=None,
    )
    out = enforce_size_budget(env)
    assert len(out["message"].encode("utf-8")) <= 8 * 1024


def test_outer_frames_dropped_before_inner():
    frames = [
        {"function": f"f{i}", "filename": "x.py", "lineno": i, "module": "x", "in_app": True}
        for i in range(200)
    ]
    # Pad each frame with bulk to force size pressure
    for f in frames:
        f["bulk"] = "x" * 2000

    env = build_envelope(
        kind="error",
        level="error",
        message="boom",
        source=None,
        environment="prod",
        release=None,
        trace_id=None,
        payload={"exception": {"type": "E", "value": "v", "frames": frames}},
    )
    out = enforce_size_budget(env)
    encoded = json.dumps(out, default=str).encode("utf-8")
    assert len(encoded) <= MAX_ENVELOPE_BYTES
    kept = out["payload"]["exception"]["frames"]
    # innermost frames are last; we should still have *some* and they
    # should be from the tail of the original list.
    assert kept
    assert kept[-1]["function"] == "f199"


def test_minimal_envelope_of_last_resort():
    # Build something pathological that can't be trimmed by frames alone.
    huge_payload = {"blob": "x" * (MAX_ENVELOPE_BYTES * 2)}
    env = build_envelope(
        kind="error",
        level="error",
        message="boom",
        source=None,
        environment="prod",
        release=None,
        trace_id=None,
        payload={"exception": {"type": "E", "value": "v", "frames": []}, **huge_payload},
    )
    out = enforce_size_budget(env)
    encoded = json.dumps(out, default=str).encode("utf-8")
    assert len(encoded) <= MAX_ENVELOPE_BYTES
    assert out["payload"].get("truncated") is True
