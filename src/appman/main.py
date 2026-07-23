"""Main module for appman."""

from __future__ import annotations

import logging
import sys

from .cli import create_parser, parse_args
from .config import init_config
from .logger import init_log

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the cli application."""
    init_config()
    init_log()
    logger.debug("Starting appman...")

    parser = create_parser()
    args = parse_args(parser)
    if hasattr(args, "func"):
        args.func(args)
    else:
        logger.error("No command provided. Help message provided:\n")
        parser.print_help()
        sys.exit(1)
