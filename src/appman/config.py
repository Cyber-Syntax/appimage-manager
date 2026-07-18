"""Configuration and logging setup for appman."""

from __future__ import annotations

import logging

from .constants import (
    APPIMAGES_DIR,
    CACHE_DIR,
    CATALOG_DIR,
    CONFIG_DIR,
    DATA_DIR,
    LOG_DIR,
)

logger = logging.getLogger(__name__)


def init_config() -> None:
    """Create xdg dirs."""
    for dirs in (
        CONFIG_DIR,
        LOG_DIR,
        DATA_DIR,
        APPIMAGES_DIR,
        CATALOG_DIR,
        CACHE_DIR,
    ):
        was_missing = not dirs.exists()
        logger.debug("Creating directory: %s", dirs)
        try:
            dirs.mkdir(parents=True, exist_ok=True)
            if was_missing:
                logger.info("Created directory: %s", dirs)
            else:
                logger.debug("Directory already exists: %s", dirs)
        except Exception:
            logger.error("Failed to create directory: %s", dirs)
            raise
