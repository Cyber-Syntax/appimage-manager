"""Constants for appman."""

import asyncio
from pathlib import Path

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

# kept well under the 60 req/hr unauthenticated
# this is separate from DOWNLOAD_SEMAPHORE
# asset download use direct url and never count against this limit.
API_CONCURRENCY = 50
API_SEMAPHORE = asyncio.Semaphore(API_CONCURRENCY)

# bounded concurrency
# downloads use github website download url and never touch the rest api
# so this semaphore is independent of API_SEMAPHORE
#
# github devs recommend max 20 for concurrent downloads
DOWNLOAD_CONCURRENCY = 20
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)

# 256 KiB, streamed, never buffer a whole AppImage in memory
CHUNK_SIZE = 1024 * 256

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

# HTTP status codes
HTTP_404 = 404
