"""Main module for appman."""

from __future__ import annotations

import logging
import sys

from .cli import parse_args
from .config import init_config
from .logger import init_log

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the cli application."""
    init_config()
    init_log()
    logger.debug("Starting appman...")

    args = parse_args()
    if args.command == "install":
        from .install import install

        install(args.url)
    else:
        logger.error("Wrong command")
        sys.exit(1)
