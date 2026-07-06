"""Path prefix matching for SDK ignore rules."""

from __future__ import annotations

from typing import Iterable

# Applied unless the customer passes additional `ignore_paths` in `init()`.
DEFAULT_IGNORE_PATHS: tuple[str, ...] = ("/static/", "/media/", "/favicon.ico")


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    return path if path.startswith("/") else f"/{path}"


def path_is_ignored(path: str, prefixes: Iterable[str]) -> bool:
    """Return True when `path` equals or starts with any normalized prefix."""
    norm = normalize_path(path)
    for prefix in prefixes:
        p = normalize_path(prefix)
        if norm == p or norm.startswith(p):
            return True
    return False
