"""Main module for appman."""

from __future__ import annotations

import logging
import sys

from .cli import parse_args
from .config import init_config
from .logger import init_log

logger = logging.getLogger(__name__)


# TODO: write good docstrings via google-style and well written comments
# for all of the functions in this and other modules!


# TODO: write proper logging for all of the other modules
# infos, warnings, errors, and debug messages...
def main() -> None:
    """Run the cli application."""
    init_config()
    init_log()

    args = parse_args()
    if args.command == "install":
        from .install import install

        install(args.url)
    else:
        logger.error("Wrong command")
        sys.exit(1)
