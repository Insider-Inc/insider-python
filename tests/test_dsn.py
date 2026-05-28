import pytest

from insider.dsn import DSN, InvalidDSNError


VALID = "https://abctoken@insider.test/123e4567-e89b-12d3-a456-426614174000"


def test_parses_valid_dsn():
    dsn = DSN.parse(VALID)
    assert dsn.scheme == "https"
    assert dsn.host == "insider.test"
    assert dsn.token == "abctoken"
    assert dsn.project_id == "123e4567-e89b-12d3-a456-426614174000"


def test_beam_url_is_under_api_v1():
    assert (
        DSN.parse(VALID).beam_url
        == "https://insider.test/api/v1/beam/123e4567-e89b-12d3-a456-426614174000/"
    )


def test_redacted_drops_token():
    assert "abctoken" not in DSN.parse(VALID).redacted()
    assert "[redacted]" in DSN.parse(VALID).redacted()


def test_supports_explicit_port():
    dsn = DSN.parse(
        "http://t@localhost:8000/123e4567-e89b-12d3-a456-426614174000"
    )
    assert dsn.host == "localhost:8000"
    assert dsn.beam_url.startswith("http://localhost:8000/api/v1/beam/")


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not-a-url",
        "ftp://t@host/123e4567-e89b-12d3-a456-426614174000",
        "https://insider.test/123e4567-e89b-12d3-a456-426614174000",  # no token
        "https://t@insider.test/",  # no project id
        "https://t@insider.test/not-a-uuid",
        "https://t@insider.test/123e4567-e89b-12d3-a456-426614174000/extra",
        "https://t:p@insider.test/123e4567-e89b-12d3-a456-426614174000",  # password
    ],
)
def test_rejects_garbage(raw):
    with pytest.raises(InvalidDSNError):
        DSN.parse(raw)


def test_parse_none_raises():
    with pytest.raises(InvalidDSNError):
        DSN.parse(None)  # type: ignore[arg-type]
