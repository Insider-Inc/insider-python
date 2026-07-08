# Changelog

All notable changes to `insider-python` are documented here.

## 0.1.9 — 2026-07-08

### Added

- SDK privacy controls: `ignore_paths`, `ignore_builtin_paths` (default
  `True` for `/static/`, `/media/`, `/favicon.ico`), `scrub_defaults`,
  `scrub_keys`, advanced `scrub={}` dict, and `header_policy`
  (`allowlist` / `all` / `none`).
- One-time init warnings when `send_default_pii=True`, `enable_logs=True`,
  or `header_policy="all"` is used without scrub configuration.
- `insider.contrib.django` reads `settings.INSIDER` and `INSIDER_*` keys for
  v1 migration (`IGNORE_PATHS`, `MASK_FIELDS`, `CAPTURE_REQUEST_BODY`).

### Changed

- Built-in sensitive-key deny-list is **opt-in** (`scrub_defaults=False` by
  default). Matched dict keys are replaced with the literal string
  `"[Filtered]"`.
- JSON request/response body strings are parsed before scrub walks nested
  keys.
- Invalid `header_policy` values fall back to `allowlist` with a debug
  warning.

### Removed

- `DjangoIntegration(ignore_admin=...)` — use `ignore_paths` in `init()`
  instead; not every app has `/admin/`.

### Fixed

- Exceptions on ignored paths no longer leak into the next request's
  footprint (`capture_request_exception` skips ignored paths).

## 0.1.7 — 2026-06-24

### Added

- Capture HTTP **response bodies** on Django WSGI/ASGI when `send_default_pii=True`
  (truncated at 8 KiB; streaming responses skipped).
- Correct `request_user` formatting when user context is a dict with `id`.

## 0.1.6 — 2026-06-19

Same as the unreleased 0.1.5 line (PyPI version slot was consumed without
a retained release). Use this version for Django ASGI support.

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
