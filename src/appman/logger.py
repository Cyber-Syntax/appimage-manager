"""Logging setup for appman.

appman keeps stdout clean for real command output, so logs and progress
messages go to stderr instead. That makes commands safe to pipe into tools
like grep or jq without extra noise.

# NOTE:
    file_handler -> it directly write file, it isn't stderr or stdout
    print        -> stdout user facing output/result only
    logger       -> info/debug etc. stderr so user pipe only prints
"""

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
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)
