"""Structured logging configuration for Pinterest Aesthetic Automation.

Provides a single entry point for configuring the root logger from a
:class:`~pinterest_agent.config.loader.LoggingConfig` instance.

Usage::

    from pinterest_agent.config.loader import ConfigLoader
    from pinterest_agent.utils.logging_setup import setup_logging

    config = ConfigLoader().load("config.yaml")
    setup_logging(config.logging)
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from pinterest_agent.config.loader import LoggingConfig

logger = logging.getLogger(__name__)


def setup_logging(config: LoggingConfig) -> None:
    """Configure the root logger with the given settings.

    * Level from *config.level*.
    * Formatter from *config.format_string*.
    * Rotating file handler if *config.file* is set.
    * Always an stdout handler (stream).

    This function is idempotent — calling it multiple times will re-configure
    the root logger each time. Call it once at the application entry point
    (``cli/main.py``) before any other code.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, config.level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates on re-config
    for handler in list(root.handlers):
        root.removeHandler(handler)

    fmt = logging.Formatter(config.format_string)

    # Always add stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(fmt)
    root.addHandler(stdout_handler)

    # Optionally add rotating file handler
    if config.file:
        try:
            file_handler = RotatingFileHandler(
                config.file,
                maxBytes=config.max_bytes,
                backupCount=config.backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(fmt)
            root.addHandler(file_handler)
            logger.info("Logging to file: %s (rotation=%s)", config.file, config.rotation)
        except (OSError, IOError) as exc:
            logger.warning("Failed to open log file %s: %s", config.file, exc)

    logger.debug("Logging configured: level=%s, file=%s", config.level, config.file)
