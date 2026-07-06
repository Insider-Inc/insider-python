"""Resolve scrub and header privacy options from `init()` arguments."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from .safety import debug

VALID_HEADER_POLICIES = frozenset({"allowlist", "all", "none"})


def resolve_scrub_options(
    *,
    scrub_defaults: bool = False,
    scrub_keys: Optional[Iterable[str]] = None,
    scrub: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str], List[str]]:
    """
    Return `(use_defaults, body_keys, header_names)`.

    Top-level `scrub_defaults` / `scrub_keys` are sugar. When `scrub` is
    passed, overlapping fields in the dict win — e.g. ``scrub={"body_keys": [...]}``
    replaces top-level ``scrub_keys`` entirely (it does not merge them).
    """
    use_defaults = bool(scrub_defaults)
    body_keys = list(scrub_keys or [])
    header_names: List[str] = []

    if scrub:
        if "defaults" in scrub:
            use_defaults = bool(scrub["defaults"])
        if "body_keys" in scrub:
            body_keys = [str(k) for k in (scrub["body_keys"] or [])]
        if "header_names" in scrub:
            header_names = [str(k) for k in (scrub["header_names"] or [])]

    return use_defaults, body_keys, header_names


def normalize_header_policy(value: Optional[str]) -> str:
    if value is None:
        return "allowlist"
    policy = str(value).lower()
    if policy not in VALID_HEADER_POLICIES:
        debug(
            f"unknown header_policy={value!r}; falling back to 'allowlist'. "
            f"Valid values: allowlist, all, none"
        )
        return "allowlist"
    return policy
