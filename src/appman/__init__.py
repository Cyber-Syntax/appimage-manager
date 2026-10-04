"""appman - A command-line tool to manage AppImages on Linux."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("appman")
except PackageNotFoundError:
    # Package is not installed
    __version__ = "0+unknown"

__all__ = ["__version__"]
