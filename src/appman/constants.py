"""Constants for appman."""

from pathlib import Path

# XDG_CONFIG_HOME: $HOME/.config
CONFIG_DIR = Path.home() / ".config" / "appman"
CONFIG_FILE = CONFIG_DIR / "config.toml"
# XDG_STATE_HOME: new user logs, history
LOG_DIR = Path.home() / ".local" / "state" / "appman"
LOG_FILE = LOG_DIR / "main.log"
# XDG_DATA_HOME: $HOME/.local/share
BACKUP_DIR = Path.home() / ".local" / "share" / "appman" / "backup"
DATA_DIR = Path.home() / ".local" / "share" / "appman"
APPIMAGES_DIR = DATA_DIR / "appimages"
CATALOG_DIR = DATA_DIR / "catalog"
# XDG_CACHE_HOME: $HOME/.cache
CACHE_DIR = Path.home() / ".cache" / "appman"
DOWNLOADS_DIR = CACHE_DIR / "downloads"


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
    "nightly",
)

INCOMPATIBLE_PLATFORM_PATTERNS = [
    # Windows patterns
    r"(?i)win(32|64)",
    r"(?i)windows",
    r"(?i)legacy.*win",
    r"(?i)portable.*win",
    # macOS patterns
    # WRONG: `r"(?i)mac(?!ro)",` because it would match emacs-x86_64.AppImage
    # The following patterns are more precise and avoid false positives:
    r"(?i)(?:^|[-_.])mac(?:os)?(?:[-_.]|$)",
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
