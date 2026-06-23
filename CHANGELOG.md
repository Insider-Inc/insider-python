# Changelog

All notable changes to `insider-python` are documented here.

## 0.1.5 — 2026-06-19

### Added

- Full Django ASGI support: `get_response_async` patch, `ASGIHandler` escape
  capture, and `wrap_asgi_application()` for Channels `ProtocolTypeRouter`.
- `response_for_exception` patch for reliable exception capture on async
  request paths.
- `sync_pending_from_request()` for cross-thread exception handoff on ASGI.
- `safe_async` helper and startup integration diagnostics (`INSIDER_DEBUG`).
- ASGI integration tests and README recipes (WSGI, plain ASGI, Channels).
- Request lifecycle beacons (`kind=request`) via `DjangoIntegration` with
  optional `auto_perf=False` when using the ASGI wrapper.

### Changed

- `DjangoIntegration` installs handler, WSGI, ASGI, signals, and DRF hooks
  with per-hook error isolation so one failure does not block the rest.
- DRF hook requires `django.setup()` before `insider.init()` (documented in
  README Channels example).

## 0.1.4 and earlier

See git history and PyPI release notes for prior adapter releases.
