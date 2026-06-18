"""Map stdlib logging levels to Insider beacon levels."""

from __future__ import annotations

import logging

LEVEL_NAMES = {
    logging.DEBUG: "debug",
    logging.INFO: "info",
    logging.WARNING: "warning",
    logging.ERROR: "error",
    logging.CRITICAL: "fatal",
}

NAME_TO_LOGGING = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.CRITICAL,
}


def insider_level(record: logging.LogRecord) -> str:
    return LEVEL_NAMES.get(record.levelno, "info")


def logging_level(name: str) -> int:
    return NAME_TO_LOGGING.get(name.lower(), logging.INFO)
