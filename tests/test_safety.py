from insider.safety import safe, set_debug


def test_safe_passes_through_return_value():
    @safe
    def works(x):
        return x * 2

    assert works(3) == 6


def test_safe_swallows_exceptions():
    @safe
    def boom():
        raise RuntimeError("nope")

    assert boom() is None


def test_safe_keeps_function_metadata():
    @safe
    def named():
        return "ok"

    assert named.__name__ == "named"


def test_debug_default_is_silent(capsys):
    set_debug(False)
    from insider.safety import debug

    debug("never shown")
    captured = capsys.readouterr()
    assert "never shown" not in captured.err


def test_debug_when_enabled_writes_to_stderr(capsys):
    set_debug(True)
    from insider.safety import debug

    debug("hello")
    captured = capsys.readouterr()
    assert "[insider] hello" in captured.err
    set_debug(False)
