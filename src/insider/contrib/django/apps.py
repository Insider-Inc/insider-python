"""
AppConfig that auto-initializes the SDK from Django settings.

We avoid importing `django.conf.settings` at module import time — Django
calls `ready()` once the settings are fully resolved, which is the safe
place to do it.
"""

from __future__ import annotations

from typing import Any, Dict

from django.apps import AppConfig

from ... import init
from ...integrations.django import DjangoIntegration
from ...safety import debug


def _insider_dict_kwargs(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Map v1 `settings.INSIDER` keys to v2 `init()` kwargs."""
    kwargs: Dict[str, Any] = {}
    if "IGNORE_PATHS" in raw:
        kwargs["ignore_paths"] = raw["IGNORE_PATHS"]
    if "MASK_FIELDS" in raw:
        kwargs["scrub_keys"] = raw["MASK_FIELDS"]
        kwargs["scrub_defaults"] = True
    if "CAPTURE_REQUEST_BODY" in raw:
        kwargs["send_default_pii"] = bool(raw["CAPTURE_REQUEST_BODY"])
    return kwargs


def _settings_kwargs() -> Dict[str, Any]:
    """Collect `INSIDER` dict and `INSIDER_*` keys into init kwargs."""
    from django.conf import settings

    kwargs: Dict[str, Any] = {}
    insider_dict = getattr(settings, "INSIDER", None)
    if isinstance(insider_dict, dict):
        kwargs.update(_insider_dict_kwargs(insider_dict))

    for setting, key in (
        ("INSIDER_DSN", "dsn"),
        ("INSIDER_ENVIRONMENT", "environment"),
        ("INSIDER_RELEASE", "release"),
        ("INSIDER_SEND_DEFAULT_PII", "send_default_pii"),
        ("INSIDER_BEFORE_SEND", "before_send"),
        ("INSIDER_SCRUB_DEFAULTS", "scrub_defaults"),
        ("INSIDER_SCRUB_KEYS", "scrub_keys"),
        ("INSIDER_HEADER_POLICY", "header_policy"),
        ("INSIDER_IGNORE_PATHS", "ignore_paths"),
        ("INSIDER_IN_APP_INCLUDE", "in_app_include"),
        ("INSIDER_TRANSPORT_QUEUE_SIZE", "transport_queue_size"),
        ("INSIDER_TRANSPORT_FLUSH_TIMEOUT", "transport_flush_timeout"),
        ("INSIDER_DEBUG", "debug"),
    ):
        value = getattr(settings, setting, None)
        if value is not None:
            kwargs[key] = value
    return kwargs


def _django_integration_kwargs() -> Dict[str, Any]:
    from django.conf import settings

    kwargs: Dict[str, Any] = {}
    ignore_admin = getattr(settings, "INSIDER_IGNORE_ADMIN", None)
    if ignore_admin is not None:
        kwargs["ignore_admin"] = bool(ignore_admin)
    return kwargs


class InsiderConfig(AppConfig):
    """Side-effect-only Django app: initialize the SDK when ready."""

    name = "insider.contrib.django"
    label = "insider_django"
    verbose_name = "Insider (telemetry)"

    def ready(self) -> None:
        try:
            kwargs = _settings_kwargs()
            integration_kwargs = _django_integration_kwargs()
        except Exception as exc:
            debug(f"settings read failed: {exc}")
            return
        dsn = kwargs.pop("dsn", None)
        init(
            dsn,
            integrations=[DjangoIntegration(**integration_kwargs)],
            **kwargs,
        )
