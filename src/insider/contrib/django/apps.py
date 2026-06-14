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


def _settings_kwargs() -> Dict[str, Any]:
    """Collect `INSIDER_*` keys from Django settings into init kwargs."""
    from django.conf import settings

    kwargs: Dict[str, Any] = {}
    for setting, key in (
        ("INSIDER_DSN", "dsn"),
        ("INSIDER_ENVIRONMENT", "environment"),
        ("INSIDER_RELEASE", "release"),
        ("INSIDER_SEND_DEFAULT_PII", "send_default_pii"),
        ("INSIDER_BEFORE_SEND", "before_send"),
        ("INSIDER_SCRUB_KEYS", "scrub_keys"),
        ("INSIDER_IN_APP_INCLUDE", "in_app_include"),
        ("INSIDER_TRANSPORT_QUEUE_SIZE", "transport_queue_size"),
        ("INSIDER_TRANSPORT_FLUSH_TIMEOUT", "transport_flush_timeout"),
        ("INSIDER_DEBUG", "debug"),
    ):
        value = getattr(settings, setting, None)
        if value is not None:
            kwargs[key] = value
    return kwargs


class InsiderConfig(AppConfig):
    """Side-effect-only Django app: initialize the SDK when ready."""

    name = "insider.contrib.django"
    label = "insider_django"
    verbose_name = "Insider (telemetry)"

    def ready(self) -> None:
        try:
            kwargs = _settings_kwargs()
        except Exception as exc:
            debug(f"settings read failed: {exc}")
            return
        # No DSN means disabled mode — `init` itself debug-logs that and
        # returns None.  We pass kwargs.pop("dsn", None) explicitly so the
        # env-var fallback in `init` still applies if Django's settings
        # didn't define it.
        dsn = kwargs.pop("dsn", None)
        init(dsn, integrations=[DjangoIntegration()], **kwargs)
