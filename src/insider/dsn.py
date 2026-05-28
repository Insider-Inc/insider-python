"""
DSN string parsing and validation.

A DSN is the single string the customer pastes into their config. It
encodes everything the SDK needs to know about which server to beam
beacons at and which credential to use:

    {scheme}://{beacon_token}@{host}/{project_public_id}

Example:

    https://abc...xyz@insider.example.com/3c29b8cb-1fe9-4b42-94a0-28d016cb20f9

The endpoint path (`/api/v1/beam/<uuid>/`) is *not* in the DSN. We hard-
code it on the SDK side so we can change the server's URL layout later
without breaking SDKs already in the wild.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import UUID


class InvalidDSNError(ValueError):
    """Raised when a DSN string can't be parsed into a usable shape."""


@dataclass(frozen=True)
class DSN:
    """A parsed DSN. Immutable; safe to share across threads."""

    scheme: str
    host: str
    token: str
    project_id: str

    @classmethod
    def parse(cls, raw: str) -> "DSN":
        if not raw or not isinstance(raw, str):
            raise InvalidDSNError("DSN must be a non-empty string.")

        parsed = urlparse(raw.strip())

        if parsed.scheme not in ("http", "https"):
            raise InvalidDSNError(
                f"DSN scheme must be http or https, got {parsed.scheme!r}."
            )
        if not parsed.username:
            raise InvalidDSNError("DSN is missing the beacon token (the userinfo part).")
        if parsed.password:
            raise InvalidDSNError(
                "DSN must not contain a password; only the beacon token belongs there."
            )
        if not parsed.hostname:
            raise InvalidDSNError("DSN is missing the host.")

        # The path is "/<project_public_id>" — strip the leading slash and any
        # trailing slash. We deliberately reject extra path components so we
        # catch typos like "/api/v1/beam/<uuid>" pasted by mistake.
        path = parsed.path.strip("/")
        if not path:
            raise InvalidDSNError("DSN is missing the project id in the path.")
        if "/" in path:
            raise InvalidDSNError(
                "DSN path must be just the project id, with no extra segments."
            )
        try:
            UUID(path)
        except ValueError as exc:
            raise InvalidDSNError(f"Project id {path!r} is not a valid UUID.") from exc

        host = parsed.hostname
        if parsed.port:
            host = f"{host}:{parsed.port}"

        return cls(
            scheme=parsed.scheme,
            host=host,
            token=parsed.username,
            project_id=path,
        )

    @property
    def beam_url(self) -> str:
        """The URL the SDK POSTs beacons to."""
        return f"{self.scheme}://{self.host}/api/v1/beam/{self.project_id}/"

    def redacted(self) -> str:
        """A safe-to-log version of the DSN with the token masked."""
        return f"{self.scheme}://[redacted]@{self.host}/{self.project_id}"
