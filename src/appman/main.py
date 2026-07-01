"""Main module for appman."""

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import orjson
import requests

# XDG_CONFIG_HOME: $HOME/.config
CONFIG_DIR = Path.home() / ".config" / "appman"
CONFIG_FILE = CONFIG_DIR / "config.toml"
# XDG_STATE_HOME: new user logs, history
LOG_DIR = Path.home() / ".local" / "state" / "appman"
LOG_FILE = LOG_DIR / "main.log"
# XDG_DATA_HOME: $HOME/.local/share
# TODO: add backup also in data home section when you add that feature
DATA_DIR = Path.home() / ".local" / "share" / "appman"
APPIMAGES_DIR = DATA_DIR / "appimages"
CATALOG_DIR = DATA_DIR / "catalog"
# XDG_CACHE_HOME: $HOME/.cache
CACHE_DIR = Path.home() / ".cache" / "appman"


def init_config() -> None:
    """Create xdg dirs."""
    for dir in (
        CONFIG_DIR,
        LOG_DIR,
        DATA_DIR,
        APPIMAGES_DIR,
        CATALOG_DIR,
        CACHE_DIR,
    ):
        dir.mkdir(parents=True, exist_ok=True)


def init_log() -> None:
    """Configure logging."""
    logger = logging.getLogger("appman")
    logger.setLevel(logging.DEBUG)

    # file handler with rotation, max 1MB, keep 5 backup
    fh = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    )

    # console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)


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


# TODO: install appimage from github url - use functional programming with dataclasses, enums -
def parse_github_url(url: str) -> tuple[str, str]:
    """Extract the repository owner and name from a GitHub URL."""
    # Regex pattern to capture owner and repo
    # Handles: https://github.com/owner/repo | https://github.com/owner/repo.git | git@github.com:owner/repo.git
    pattern = r"(?:https?://github\.com/|git@github\.com:)(?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?"

    match = re.search(pattern, url)
    if not match:
        msg = f"Invalid or unsupported GitHub URL: '{url}'"
        raise ValueError(msg)

    return match.group("owner"), match.group("repo")


# 4. create new function to request via github api to get json file in return
def fetch_latest_release(owner: str, repo: str) -> dict[str, Any]:
    """Fetch latest release from github."""
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


# 5. save it to the cache while still on memory
def cache_release_data(owner: str, repo: str, data: dict[str, Any]) -> None:
    cache_path = CACHE_DIR / f"{owner}_{repo}_latest.json"

    with cache_path.open("wb") as file:
        file.write(orjson.dumps(data))


# 6. make a function to asset selection that find .appimage from that json assets
# API ASSET FILTERING
#
# These keywords are used to filter out unstable
# or incompatible assets from the API response.
UNSTABLE_VERSION_KEYWORDS = (
    "experimental",
    "beta",
    "alpha",
    "rc",
    "pre",
    "dev",
    "test",
    "nightly",
)

INCOMPATIBLE_PLATFORM_PATTERNS = [
    # Windows patterns
    r"(?i)win(32|64)",
    r"(?i)windows",
    r"(?i)legacy.*win",
    r"(?i)portable.*win",
    # macOS patterns
    r"(?i)mac(?!ro)",
    r"(?i)darwin",
    r"(?i)osx",
    r"(?i)(?:^|[-_.])apple(?:[-_.]|$)",
    # ARM-specific YAML files
    r"(?i)latest.*arm.*\.ya?ml$",
    r"(?i)arm.*latest.*\.ya?ml$",
    # macOS-specific YAML files
    r"(?i)latest.*mac.*\.ya?ml$",
    r"(?i)mac.*latest.*\.ya?ml$",
    # ARM architecture patterns
    r"(?i)arm64",
    r"(?i)aarch64",
    r"(?i)armv7l?",
    r"(?i)armhf",
    r"(?i)armv6",
    # Source archive patterns
    r"(?i)[-_.]src[-_.]",
    r"(?i)[-_.]source[-_.]",
    # Experimental builds
    r"(?i)experimental",
    r"(?i)qt6.*experimental",
]

INCOMPATIBLE_PLATFORM_EXTENSIONS = (
    ".msi",
    ".exe",
    ".dmg",
    ".pkg",
)

def select_appimage_asset(assets: )
# 7. find the download url in that found .appimage asset
# 8. request download for that appimage
# 9. rename appimage to it's own repo - e.g clear the versions from the appimage to make your life easier for desktop creation -
# 9. save it to appimages dir
# 10. extract icon from appimage
# 11. create .desktop for it - because of name is cleared from version, desktop creation is going to be stay same on update command in future -
# 12. chmod +x to appimage


class AssetType(Enum):
    APPIMAGE = "AppImage"
    CHECKSUM_FILE = "checksum_file"
    DIGEST = "github_digest"


@dataclass(frozen=True)
class Asset:
    name: str
    download_url: str
    size: int
    asset_type: AssetType
    hash: str


def main() -> None:
    """Run the cli application"""
    init_config()
    init_log()

    args = parse_args()
    if args.command == "install":
        install(args.url)
    else:
        print("Wrong command")
        sys.exit(1)
