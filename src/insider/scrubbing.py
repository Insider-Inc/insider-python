"""
Default and custom data scrubbing.

This is the SDK-side defence against accidental PII / secret leakage.
We assume the customer's code routinely has dicts named `headers`,
`form`, `cookies`, etc. that contain sensitive values, and that we are
about to serialize and ship those dicts off-host. So before we do, we
walk the structure and mask any key name that looks dangerous.

Match is case-insensitive on the *key name only*. We never inspect
values for sensitive content (regex-on-everything is expensive and
unreliable). If a customer wants extra keys filtered they pass
`scrub_keys=[...]` into `init`, and the deny-list grows.

A future phase can add value-level patterns (credit-card regex, etc.)
but the v1 contract is "we mask anything whose key looks scary."
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Set

# Lowercase. Match is `key.lower() in DEFAULT_DENY_KEYS`.
DEFAULT_DENY_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "authorization",
        "auth",
        "x-api-key",
        "cookie",
        "set-cookie",
        "session",
        "sessionid",
        "csrf",
        "csrftoken",
        "x-csrf-token",
        "credit_card",
        "card_number",
        "cc_number",
        "cvv",
        "ssn",
    }
)

FILTERED = "[Filtered]"

# Walk depth cap. Pathological customer payloads (deeply nested dicts) shouldn't
# burn the SDK's stack or budget. Anything deeper than this is replaced with a
# marker — the customer's data was already going to be lossily truncated by
# the size budget anyway.
_MAX_DEPTH = 16


def build_deny_set(
    extra_keys: Optional[Iterable[str]] = None,
    *,
    use_defaults: bool = True,
) -> Set[str]:
    """Build a deny-list; built-in keys are included only when `use_defaults=True`."""
    deny: Set[str] = set()
    if use_defaults:
        deny.update(DEFAULT_DENY_KEYS)
    if extra_keys:
        deny.update(k.lower() for k in extra_keys if isinstance(k, str))
    return deny


def scrub(
    data: Any,
    *,
    extra_keys: Optional[Iterable[str]] = None,
    use_defaults: bool = True,
) -> Any:
    """
    Return a new structure with sensitive values replaced by `[Filtered]`.
    The input is not mutated.
    """
    deny = build_deny_set(extra_keys, use_defaults=use_defaults)
    return _scrub(data, deny, depth=0)


def scrub_header_map(
    headers: Dict[str, Any],
    *,
    extra_names: Optional[Iterable[str]] = None,
    use_defaults: bool = True,
) -> Dict[str, Any]:
    """Redact header values whose names match the deny-list."""
    deny = build_deny_set(extra_names, use_defaults=use_defaults)
    return {
        k: (FILTERED if isinstance(k, str) and k.lower() in deny else v)
        for k, v in headers.items()
    }


def _scrub(value: Any, deny: Set[str], depth: int) -> Any:
    if depth > _MAX_DEPTH:
        return "[TooDeep]"
    if isinstance(value, dict):
        return {
            k: (FILTERED if isinstance(k, str) and k.lower() in deny
                else _scrub(v, deny, depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        scrubbed = [_scrub(item, deny, depth + 1) for item in value]
        return scrubbed if isinstance(value, list) else tuple(scrubbed)
    return value
