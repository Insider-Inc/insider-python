# Demo Django app for insider-python

Smallest possible Django project that exercises the `insider.contrib.django`
integration end-to-end against a running Insider server.

## Setup

From the SDK root (`sdk/python/`):

```bash
source .venv/bin/activate
pip install -e ".[django]"
```

Set your DSN. The demo reads it from the environment so you don't bake
secrets into source:

```bash
export INSIDER_DSN="https://<beacon_token>@localhost:8000/<project_uuid>"
export INSIDER_ENVIRONMENT="demo"
export INSIDER_RELEASE="demo-0.1.0"
```

Run the demo:

```bash
cd examples/demo_django
python manage.py runserver 8001
```

Then visit:

- `http://localhost:8001/` — succeeds, no Beacon emitted.
- `http://localhost:8001/boom/` — raises `ValueError`, captured by the
  middleware, sent as a Beacon to your Insider server.
- `http://localhost:8001/notice/` — sends a manual `capture_message`.

Look at the Insider dashboard (or the `/api/v1/beacons/` API) — the
Beacons should be there within a second or two.
