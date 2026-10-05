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

_CONSOLE_HANDLER = "_appman_console_handler"
_FILE_HANDLER = "_appman_file_handler"


def _remove_handler(logger: logging.Logger, marker: str) -> None:
    """Remove a handler from the logger by marker attribute.

    Args:
        logger: The logger from which to remove the handler.
        marker: The marker attribute to identify the handler to remove.
    """
    # Iterate over a copy of the logger's handlers. loop over a copy of
    # the list to avoid modifying it while iterating.
    for handler in logger.handlers[:]:
        # look for the marker attribute on the handler to identify it
        if getattr(handler, marker, False):
            logger.removeHandler(handler)
            # Close the handler to release resources(e.g log file).
            handler.close()


def init_console_log() -> None:
    """Configure console logging.

    This function sets up a console handler for the 'appman' logger,
    directing INFO and higher level logs to stderr. It also removes any
    existing console handlers to prevent duplicate logs. This need
    to be called before init_config() to ensure that any errors during
    config initialization are logged to the console.
    """
    # configure the top-level appman logger. Module loggers such as
    # "appman.api" are child loggers and can propagete their records
    # to this "appman" logger.
    logger = logging.getLogger("appman")
    logger.setLevel(logging.DEBUG)
    _remove_handler(logger, _CONSOLE_HANDLER)

    # console handler
    handler = logging.StreamHandler(sys.stderr)
    setattr(
        handler, _CONSOLE_HANDLER, True
    )  # handler._appman_console_handler = True
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


def init_file_log() -> None:
    """Attach the rotating file handler.

    This function sets up a rotating file handler for the 'appman' logger,
    directing DEBUG and higher level logs to a specified log file. It also
    removes any existing file handlers to prevent duplicate logs. This should
    be called after init_config() to ensure that the log directory exists.
    """
    logger = logging.getLogger("appman")
    _remove_handler(logger, _FILE_HANDLER)

    # file handler with rotation, max 1MB, keep 5 backup
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5)
    setattr(
        handler, _FILE_HANDLER, True
    )  # handler._appman_file_handler = True
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    )
    logger.addHandler(handler)
