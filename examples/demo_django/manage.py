#!/usr/bin/env python
"""Entrypoint for the demo Django project."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo_django.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django isn't installed; run `pip install insider-python[django]`."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
