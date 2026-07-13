"""Configuration and logging setup for appman."""

from .constants import (
    APPIMAGES_DIR,
    CACHE_DIR,
    CATALOG_DIR,
    CONFIG_DIR,
    DATA_DIR,
    LOG_DIR,
)


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
        dirs.mkdir(parents=True, exist_ok=True)
