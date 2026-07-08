"""Application logging configuration: a rotating file handler under the app log directory."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_NAME = "herpetoid"
_MAX_BYTES = 1_000_000
_BACKUPS = 3


def configure_logging(log_dir: Path, *, level: int = logging.INFO) -> logging.Logger:
    """Attach a rotating file handler to the ``herpetoid`` logger (idempotent)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    if any(isinstance(handler, RotatingFileHandler) for handler in logger.handlers):
        return logger
    handler = RotatingFileHandler(
        log_dir / "herpetoid.log", maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    return logger
