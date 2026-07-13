import logging
import sys
from logging.handlers import RotatingFileHandler

from .constants import LOG_FILE


def init_log() -> None:
    """Configure logging."""
    logger = logging.getLogger("appman")
    logger.setLevel(logging.DEBUG)

    # file handler with rotation, max 1MB, keep 5 backup
    fh = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    )

    # console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)
