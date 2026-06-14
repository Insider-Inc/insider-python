# insider-python

The Python SDK for [Insider](https://insider.moraks.cloud/).

Beam Beacons from your Python service to your Insider server with a
one-line setup. No runtime overhead on your request path. Never raises
into your code, no matter what.

## Install

```bash
pip install insider-python
```

For the Django integration:

```bash
pip install "insider-python[django]"
```

## Quick start

### Plain Python

```python
import insider

insider.init(
    dsn="https://<beacon_token>@insider.example.com/<project_uuid>",
    environment="production",
    release="1.2.3",
)

try:
    risky()
except Exception as exc:
    insider.capture_exception(exc)

insider.capture_message("cache miss spiked", level="warning")
```

### Django

Initialize in `wsgi.py` (or `asgi.py`) before `get_wsgi_application()`:

```python
import os
import insider
from insider.integrations.django import DjangoIntegration

insider.init(
    dsn=os.environ.get("INSIDER_DSN"),
    environment="production",
    release="1.2.3",
    integrations=[DjangoIntegration()],
)

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

That's the whole setup. Every unhandled exception in a view — including
Django REST Framework API views — is now a Beacon in your dashboard.
No middleware, no `INSTALLED_APPS`, and no `EXCEPTION_HANDLER` wiring.

**Legacy setup** (still supported): add `insider.contrib.django` to
`INSTALLED_APPS` and `InsiderMiddleware` to `MIDDLEWARE`. Prefer the
`wsgi.py` pattern for new projects.

## Configuration

Order of precedence (first wins):

1. Keyword args to `insider.init(...)`.
2. `INSIDER_*` environment variables.
3. Django settings (when the Django integration is active).
4. Hard-coded defaults.

If no DSN is found anywhere, the SDK enters **disabled mode**: every
public call is a no-op, no thread starts, no socket opens.

| Option | Default | Notes |
|--------|---------|-------|
| `dsn` | env `INSIDER_DSN` | If absent, SDK is disabled |
| `environment` | `"production"` | Top-level Beacon field |
| `release` | `None` | Top-level Beacon field |
| `send_default_pii` | `False` | Required to capture `user.id`, request bodies |
| `before_send` | `None` | `(beacon) -> beacon | None` hook |
| `scrub_keys` | `None` | Extra keys to filter (added to the default deny-list) |
| `in_app_include` | `None` | Filename prefixes considered "your code" |
| `transport_queue_size` | `1000` | Bounded; drops on overflow |
| `transport_flush_timeout` | `2.0` | Seconds. Used by `close()` / `flush()` |
| `debug` | `False` | Print SDK's own warnings to stderr |

## Promise

The SDK never raises into your code. Every public function catches
`Exception` at its boundary; if something goes wrong inside the SDK,
you get nothing back and a debug log (if enabled). Your app keeps
running.

## License

MIT
