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
```

Out-of-band events (background jobs, explicit calls) use standalone beacons:
`capture_exception`, `capture_log`, `capture_perf`.

### Django

Initialize in `wsgi.py` or `asgi.py` **before** `get_wsgi_application()` /
`get_asgi_application()`:

#### WSGI (Gunicorn)

```python
import os
import insider
from insider.integrations.django import DjangoIntegration
from insider.integrations.logging import LoggingIntegration

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

insider.init(
    dsn=os.environ.get("INSIDER_DSN"),
    environment="production",
    release="1.2.3",
    enable_logs=True,
    integrations=[DjangoIntegration(), LoggingIntegration()],
)

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

#### ASGI (Daphne / Uvicorn — plain Django)

```python
import os
import insider
from insider.integrations.django import DjangoIntegration
from insider.integrations.logging import LoggingIntegration

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

insider.init(
    dsn=os.environ.get("INSIDER_DSN"),
    environment="production",
    release="1.2.3",
    enable_logs=True,
    integrations=[DjangoIntegration(), LoggingIntegration()],
)

from django.core.asgi import get_asgi_application
application = get_asgi_application()
```

#### ASGI + Channels (`ProtocolTypeRouter`)

Wrap only the HTTP branch; disable handler auto-perf to avoid double capture:

```python
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

import django

django.setup()

import insider
from insider.integrations.django import DjangoIntegration
from insider.integrations.django.asgi import wrap_asgi_application
from insider.integrations.logging import LoggingIntegration

insider.init(
    dsn=os.environ.get("INSIDER_DSN"),
    environment="production",
    enable_logs=True,
    integrations=[DjangoIntegration(auto_perf=False), LoggingIntegration()],
)

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

application = ProtocolTypeRouter({
    "http": wrap_asgi_application(get_asgi_application()),
    "websocket": URLRouter(websocket_urlpatterns),
})
```

Set `INSIDER_DEBUG=true` to print which hooks installed at startup.

That's the whole setup. **Every HTTP request** emits **one** `kind=request`
beacon containing:

- timing (duration, method, path, status)
- request context (headers, path, query string)
- stdlib logs during that request (when `enable_logs=True`)
- unhandled exception + stack trace (when the request fails)

No middleware, no `INSTALLED_APPS`, and no `EXCEPTION_HANDLER` wiring.

Disable auto capture on high-traffic apps until sampling lands:

```python
integrations=[DjangoIntegration(auto_perf=False)]
```

### Logging

During an HTTP request, stdlib `logging` lines are **buffered into the
request envelope** — not beamed as separate rows:

```python
import logging

logger = logging.getLogger(__name__)
logger.info("checkout completed")  # → payload.logs[] on the request beacon
```

Requires `enable_logs=True`, `LoggingIntegration()`, and a configured
logger level (see your app's `LOGGING` settings).

Outside an HTTP request, stdlib logs still beam as standalone `kind=log`
beacons. For explicit structured events, use `capture_log()`:

```python
insider.capture_log(
    "User checkout completed",
    level="info",
    source="checkout.service",
    tags={"feature": "checkout"},
)
```

Manual perf timings (Celery, custom spans):

```python
insider.capture_perf(
    op="celery.tasks.send_email",
    duration_ms=842,
)
```

## Footprint kinds

| Kind | When |
|------|------|
| `request` | One per HTTP request (DjangoIntegration) |
| `error` | Manual `capture_exception()` outside request cycle |
| `log` | Manual `capture_log()` or stdlib logs outside request cycle |
| `perf` | Manual `capture_perf()` for non-HTTP timings |

## Configuration

If no DSN is found anywhere, the SDK enters **disabled mode**: every
public call is a no-op.

| Option | Default | Notes |
|--------|---------|-------|
| `dsn` | env `INSIDER_DSN` | If absent, SDK is disabled |
| `environment` | `"production"` | Top-level Footprint field |
| `release` | `None` | Top-level Footprint field |
| `enable_logs` | `False` | Buffer stdlib logs into request envelopes |
| `send_default_pii` | `False` | Required to capture request bodies |
| `ignore_paths` | built-ins + custom | Skip footprints for path prefixes |
| `scrub_defaults` | `False` | Opt in to built-in sensitive-key deny-list |
| `scrub_keys` | `[]` | Extra key names to redact in bodies |
| `header_policy` | `"allowlist"` | `"all"` or `"none"` for advanced use |
| `debug` | `False` | Print SDK warnings to stderr |

### Privacy

Production apps typically add path ignores and keep bodies off:

```python
insider.init(
    dsn=os.environ["INSIDER_DSN"],
    ignore_paths=["/health", "/metrics"],
    send_default_pii=False,
)
```

When capturing bodies (`send_default_pii=True`), enable scrubbing:

```python
insider.init(
    dsn=os.environ["INSIDER_DSN"],
    send_default_pii=True,
    scrub_defaults=True,
    scrub_keys=["pin", "account_number"],
)
```

See [security-compliance.md](../docs/security-compliance.md) for advanced
options (`scrub={...}`, `header_policy`, `before_send`).

## Promise

The SDK never raises into your code.

## License

MIT
