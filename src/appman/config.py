"""Config setups for appman."""

from __future__ import annotations

import logging

from .constants import (
    APPIMAGES_DIR,
    BACKUP_DIR,
    CACHE_DIR,
    CATALOG_DIR,
    CONFIG_DIR,
    DATA_DIR,
    DOWNLOADS_DIR,
    LOG_DIR,
)

logger = logging.getLogger(__name__)


def init_config() -> None:
    """Create XDG supported config dirs.

    Raises:
        OSError: If a directory cannot be created (e.g. permission denied).
            Not caught — a broken XDG setup must surface as a hard failure.
    """
    for dirs in (
        CONFIG_DIR,
        LOG_DIR,
        DATA_DIR,
        APPIMAGES_DIR,
        CATALOG_DIR,
        CACHE_DIR,
        BACKUP_DIR,
        DOWNLOADS_DIR,
    ):
        try:
            # Check if the directory exists before attempting to create it.
            # Keep it inside try to catch PermissionError from Path.exists()
            was_missing = not dirs.exists()
            logger.debug("Creating directory: %s", dirs)

            # NOTE:
            # parents: make it create parent dirs like if ~/.config parent
            # not exist when ~/.config/appman/, than it create config, appman
            #
            # exist_ok: call the mkdir even dir exist but call is harmless
            # which cover existence check internally and do nothing if exist
            dirs.mkdir(parents=True, exist_ok=True)

            # Write good log messages for user feedback and debugging
            if was_missing:
                logger.info("Created directory: %s", dirs)
            else:
                logger.debug("Directory already exists: %s", dirs)
        except OSError:
            logger.exception("Failed to create directory: %s", dirs)
            raise
