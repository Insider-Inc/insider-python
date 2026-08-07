# Changelog

All notable changes to `insider-python` are documented here.

## 0.1.12 — 2026-08-07

### Fixed

- Footprint `ip_address` now takes only the first hop from
  `X-Forwarded-For` (and strips a trailing `:port` on IPv4). Behind GCLB /
  nginx a comma-separated list was sent raw, Insider's
  `GenericIPAddressField` rejected the beam with HTTP 400, and the SDK
  dropped the footprint.
- The `[django]` optional extra no longer depends on `django>=4.2`.
  Installing `insider-python[django]` was upgrading host apps off their
  pinned Django (e.g. 4.1.x on Python 3.8). Use `pip install insider-python`
  — Django stays the app's dependency; `DjangoIntegration` imports it at
  runtime.

## 0.1.11 — 2026-08-06

### Fixed

- `LoggingIntegration` survives Django's `logging.config.dictConfig` (and
  `fileConfig`) after `insider.init()` runs before `get_wsgi_application()`.
  The SDK re-attaches its root handler automatically — integrators do not
  need a post-setup hook.

## 0.1.10 — 2026-07-08

### Fixed

- Django footprints no longer show `request_user: anonymous` on
  authenticated requests when `send_default_pii=True`. The SDK re-reads
  `request.user` in `_finalize_request_cycle` after auth middleware and DRF
  JWT run, including when `auto_perf=False` (ASGI / Channels wrapper path).
- User capture now requires `user.is_authenticated` (via shared
  `authenticated_user_payload()`), with DRF request resolution preserved.

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
