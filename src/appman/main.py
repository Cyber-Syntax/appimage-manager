"""Main module for appman."""

from __future__ import annotations

import logging
import sys

from .cli import parse_args
from .config import init_config
from .logger import init_log

logger = logging.getLogger(__name__)


# TODO: currently we are able to install qownnotes via github url install
# test is that appimage work as expected
# make sure the logger is show verification hashes etc. on the logger
# manually test it on your own
# write unit test for the current install flow
# write integration test for the current install flow
# write e2e test for the current install flow
# make sure %80 of the code is covered by tests
# publish v0.1.0-alpha without adding any other features
# refactor your todos in v0.2.0-alpha to
# chmod +x, app rename, app move, .desktop creation, icon creation
# v0.3.0-alpha need progress bar etc.
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
