"""Demo Django settings. Reads Insider config from the environment."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "demo-only-not-secret"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "demoapp",
    "insider.contrib.django",
]

MIDDLEWARE = [
    "insider.contrib.django.middleware.InsiderMiddleware",
]

ROOT_URLCONF = "demo_django.urls"
USE_TZ = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "demo.sqlite3",
    }
}

INSIDER_DSN = os.environ.get("INSIDER_DSN")
INSIDER_ENVIRONMENT = os.environ.get("INSIDER_ENVIRONMENT", "demo")
INSIDER_RELEASE = os.environ.get("INSIDER_RELEASE", "demo-0.1.0")
INSIDER_DEBUG = os.environ.get("INSIDER_SDK_DEBUG", "0") == "1"
