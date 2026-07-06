import insider
from insider.client import _client


def test_capture_message_records_envelope(sdk_client, fake_transport):
    insider.capture_message("hello world", level="info", tags={"role": "test"})
    assert len(fake_transport.envelopes) == 1
    env = fake_transport.envelopes[0]
    assert env["kind"] == "log"
    assert env["level"] == "info"
    assert env["message"] == "hello world"
    assert env["environment"] == "test"
    assert env["payload"]["tags"] == {"role": "test"}


def test_capture_message_auto_fills_source(sdk_client, fake_transport):
    insider.capture_message("ping")
    env = fake_transport.envelopes[0]
    assert env["source"] is not None
    assert "test_capture_message_auto_fills_source" in env["source"] or "tests" in env["source"]


def test_capture_exception_extracts_frames(sdk_client, fake_transport):
    def deep():
        raise ValueError("kaboom")

    try:
        deep()
    except ValueError as exc:
        insider.capture_exception(exc, tags={"area": "checkout"})

    assert len(fake_transport.envelopes) == 1
    env = fake_transport.envelopes[0]
    assert env["kind"] == "error"
    assert env["level"] == "error"
    assert env["message"] == "kaboom"
    block = env["payload"]["exception"]
    assert block["type"] == "ValueError"
    assert block["value"] == "kaboom"
    assert any(f["function"] == "deep" for f in block["frames"])
    assert env["payload"]["tags"] == {"area": "checkout"}


def test_capture_exception_with_cause_chain(sdk_client, fake_transport):
    try:
        try:
            raise ValueError("inner")
        except ValueError as inner:
            raise RuntimeError("outer") from inner
    except RuntimeError as exc:
        insider.capture_exception(exc)

    env = fake_transport.envelopes[0]
    block = env["payload"]["exception"]
    assert block["type"] == "RuntimeError"
    assert "chain" in block
    assert block["chain"][0]["type"] == "ValueError"


def test_scrubbing_runs_on_payload(sdk_client, fake_transport):
    sdk_client.scrub_defaults = True
    insider.capture_message(
        "ping",
        extra={"password": "hunter2", "ok": "yes"},
    )
    env = fake_transport.envelopes[0]
    assert env["payload"]["extra"]["password"] == "[Filtered]"
    assert env["payload"]["extra"]["ok"] == "yes"


def test_before_send_can_drop(sdk_client, fake_transport):
    sdk_client.before_send = lambda env: None
    insider.capture_message("dropped")
    assert fake_transport.envelopes == []


def test_before_send_can_mutate(sdk_client, fake_transport):
    def hook(env):
        env["payload"]["tags"] = {"hooked": True}
        return env

    sdk_client.before_send = hook
    insider.capture_message("ping")
    assert fake_transport.envelopes[0]["payload"]["tags"] == {"hooked": True}


def test_before_send_exception_drops_beacon(sdk_client, fake_transport):
    def bad(env):
        raise RuntimeError("oh no")

    sdk_client.before_send = bad
    insider.capture_message("ping")
    assert fake_transport.envelopes == []


def test_capture_without_init_is_noop():
    # Active sdk_client is cleared by autouse fixture before each test.
    from insider.client import _set_active

    _set_active(None)
    assert insider.capture_message("ping") is None
    assert insider.capture_exception(ValueError("x")) is None


def test_init_with_no_dsn_returns_none(monkeypatch):
    monkeypatch.delenv("INSIDER_DSN", raising=False)
    assert insider.init() is None
    assert _client() is None
