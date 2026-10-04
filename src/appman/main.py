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
    # NOTE: init_config() and init_log() are called after parse_args() because
    # --version and --help are handled by argparse before any subcommand is invoked.

    # build the whole parser tree...
    parser = create_parser()
    # parse the arguments like install, URLs
    args = parse_args(parser)

    # mkdir xdg config locations
    init_config()
    # init file and console logger
    init_log()
    logger.debug("Starting appman...")

    # when `appman install` passed, hasattr is True because
    # install_parser.set_defaults to install_cmd(see cli.py)
    if hasattr(args, "func"):
        args.func(args)
    else:
        logger.error("No command provided. Help message provided:\n")
        # this is the outer parser, so it prints the top-level usage
        parser.print_help()
        sys.exit(1)
