"""Command line interface for appman."""

import argparse

from . import __version__
from .install import install


def install_cmd(args: argparse.Namespace) -> None:
    """Install command."""
    install(args.url)


def parse_args(parser: argparse.ArgumentParser) -> argparse.Namespace:
    """Parse command line arguments."""
    return parser.parse_args()


def create_parser() -> argparse.ArgumentParser:
    """Cli flag, command creation parser."""
    parser = argparse.ArgumentParser(
        prog="appman", description="AppImage manager", add_help=False
    )

    # Global flags
    _ = parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"appman {__version__}",
        help="Show version information",
    )
    _ = parser.add_argument(
        "-h", "--help", action="help", help="Show this help message"
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", required=False)

    # install command
    install_parser = subparsers.add_parser(
        "install",
        help="Install AppImage from GitHub URL",
        description="Install AppImage from GitHub URL",
        epilog="""
Example usage:
    appman install https://github.com/pbek/QOwnNotes
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _ = install_parser.add_argument(
        "url",
        help="GitHub release URL (e.g. https://github.com/owner/repo)",
    )

    install_parser.set_defaults(func=install_cmd)

    return parser
