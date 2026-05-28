"""Minimal Django settings for the integration tests."""

SECRET_KEY = "insider-sdk-tests"
DEBUG = True
ALLOWED_HOSTS = ["*", "testserver"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
ROOT_URLCONF = "tests.django_urls"
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "insider.contrib.django",
]

MIDDLEWARE = [
    "insider.contrib.django.middleware.InsiderMiddleware",
]

# Intentionally no INSIDER_DSN by default. Tests that exercise the
# middleware with an active client install one programmatically.
