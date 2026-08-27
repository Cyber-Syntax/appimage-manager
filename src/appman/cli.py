"""CLI layer for appman.

Note:
    ArgumentParser:
        defines the CLI rules:
            - Creating the command(install..), arguments(URLs), options(-h, -v)
    Namespace:
        contains the values after those rules are parsed:
            ```
            args = Namespace(
                command="install",
                urls=["url1", "url2"],
            )
            ``` -> in this example, Namespace stores names and their values:
                    args.command = "install"
                    args.urls = ["url1", "url2"]

Install Architecture flow example:
    create_parser()
        ↓
    ArgumentParser
        ↓ parse_args()
    Namespace
        ↓
    install_cmd(args)
        ↓
    install(args.urls)
"""

from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter

from . import __version__
from .install import install


def install_cmd(args: Namespace) -> None:
    """Run the install command using parsed CLI args.

    Translating the generic Namespace argparse into the specific
    call signature install() in install.py wants. install() itself
    doesn't know anything about argparser or CLI parsing, it just takes
    a list[str] of URLs.

    Example:
        install(args.urls)   # install(["https://github.com/pbek/QOwnNotes"])

    Args:
        args: Parsed command-line args containing the URLs to install.

    Returns:
        None

    Raises:
        SystemExit: Propagated from install(). Exit code 1 on partial/total
            failure, per install.py's contract (this is a documented CLI
            contract, not an implementation detail).
    """
    install(args.urls)


def parse_args(parser: ArgumentParser) -> Namespace:
    """Parse the user's command-line arguments.

    Basically use parser: ArgumentParser as argument and return
    as Namespace to be able to use it in install_cmd like args.urls.
    Uses argparse.ArgumentParser class parse_args() method.

    Args:
        parser: Configured argument parser used to interpret sys.argv.

    Returns:
        A Namespace containing the parsed command-line values.
    """
    return parser.parse_args()


def create_parser() -> ArgumentParser:
    """CLI flag, command creation parser.

    Basically create ArgumentParser, add subcommand etc. and return
    the ArgumentParser(those rules).

    Returns:
        An ArgumentParser configured with appman's global options
        and subcommands
    """
    # top level parser that understand appman and its global options
    parser = ArgumentParser(
        prog="appman", description="AppImage manager", add_help=False
    )

    # Global flags
    _ = parser.add_argument(
        "-v",
        "--version",
        action="version",  # `-v` print version and sys.exit(0) anywhere
        version=f"appman {__version__}",
        help="Show version information",
    )
    _ = parser.add_argument(
        "-h", "--help", action="help", help="Show this help message"
    )

    # subcommands such as install is store it as `args.command = "install"`
    # required false means running bare "appman" without install would
    # allowed which main.py would show help if command not provided.
    subparsers = parser.add_subparsers(dest="command", required=False)

    # install subcommand
    install_parser = subparsers.add_parser(
        "install",
        help="Install AppImage from GitHub URL",
        description="Install AppImage from GitHub URL",
        epilog="""
Example usage:
    appman install https://github.com/pbek/QOwnNotes https://github.com/super-productivity/super-productivity
        """,
        formatter_class=RawDescriptionHelpFormatter,
    )

    # add arguments like URLs
    # example list: args.urls = ["urlA", "urlB", "urlC"]
    _ = install_parser.add_argument(
        "urls",
        nargs="+",  # one or more values, collect them into a list.
        metavar="URLs",
        help="GitHub release URLs (e.g. https://github.com/owner/repo)",
    )

    # add the default command for the install_parser
    install_parser.set_defaults(func=install_cmd)

    return parser
