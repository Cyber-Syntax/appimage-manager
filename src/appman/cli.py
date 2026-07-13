"""Command line interface for appman."""

import argparse


# FIXME: type errors
def parse_args() -> argparse.Namespace:
    """Cli flag, command creation parser."""
    parser = argparse.ArgumentParser(
        prog="appman", description="AppImage manager"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # install command
    install_parser = subparsers.add_parser(
        "install", help="Install AppImage from GitHub URL"
    )
    install_parser.add_argument(
        "url", help="GitHub release URL (e.g. https://github.com/owner/repo"
    )

    return parser.parse_args()
