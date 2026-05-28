"""
Django integration for insider-python.

How to enable:

    # settings.py
    INSTALLED_APPS = [
        ...
        "insider.contrib.django",
    ]

    MIDDLEWARE = [
        ...
        "insider.contrib.django.middleware.InsiderMiddleware",
    ]

    INSIDER_DSN = "https://<token>@insider.example.com/<project_uuid>"
    INSIDER_ENVIRONMENT = "production"
    INSIDER_RELEASE = "1.2.3"

The `AppConfig.ready()` hook reads `INSIDER_*` from settings and calls
`insider.init(...)`. If no DSN is configured (`INSIDER_DSN` absent or
empty), the SDK enters disabled mode and the middleware becomes a
no-op.
"""

default_app_config = "insider.contrib.django.apps.InsiderConfig"
