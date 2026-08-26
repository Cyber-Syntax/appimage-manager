"""Logging setup for appman.

appman keeps stdout clean for real command output:
    - Console logs and progress messages go to stderr, while logs are also
        written to a rotating log file. That makes commands safe to pipe
        into tools like grep or jq without extra noise.

# NOTE:
    file_handler: writes directly to the log file; it doesn't
        use stdout/stderr
    print: stdout user facing output/result only
    logger: Console INFO+ logs go to stderr, while DEBUG+ logs are written
        to the file.

logging.getLogger(name) is a singleton factory. Every call with the same string returns the exact same Logger object out of Python's internal global registry (logging.Logger.manager.loggerDict). It's not creating a new independent thing each time.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler

from .constants import LOG_FILE


def init_log() -> None:
    """Configure logging by creating file and console handler."""
    # configure the top-level appman logger. Module loggers such as
    # "appman.api" are child loggers and can propagete their records
    # to this "appman" logger.
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
