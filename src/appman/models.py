"""Canonical data models, typed error/warning codes, and message tables.

Every dataclass here is the single source of truth referenced elsewhere
(cli.py, config.py, install.py, update.py, api.py, file_ops.py). If you add
a field, update the JSON state schema examples and config.py migration
logic in the same PR (AGENTS.md §9).

Nothing in this module raises. Business-outcome failures are represented
as data (PackageError / PackageWarning), never exceptions, per AGENTS.md §6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

# TODO: refactor google style docstrings

# ---------------------------------------------------------------------------
# Asset classification
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DownloadedAsset:
    """A single asset that has been written to disk."""

    asset: Asset
    path: Path


class AssetType(Enum):
    APPIMAGE = "AppImage"
    CHECKSUM_FILE = "checksum_file"


@dataclass(frozen=True, slots=True)
class Asset:
    """A single raw release asset, parsed from the GitHub API response."""

    name: str
    download_url: str
    size: int
    asset_type: AssetType
    # GitHub API-embedded digest, e.g. "sha256:abc123..." -> stored hex-only.
    # None if GitHub didn't supply one for this asset.
    digest: str | None


# ---------------------------------------------------------------------------
# Core domain dataclasses (ARCHITECTURE.md §6)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AppConfig:
    """Per-app persisted config (state JSON), one file per installed app."""

    name: str
    repo: str
    installed_version: str
    appimage_path: Path
    desktop_file_path: Path | None = None
    icon_path: Path | None = None
    skip_verify: bool = False
    created_from_catalog: bool = True
    catalog_id: str | None = None


@dataclass(slots=True)
class CatalogEntry:
    """Maintainer-curated override for a catalog app.

    Catalog rules always take precedence over generic GitHub-inferred
    defaults (AGENTS.md §5). `allow_skip_verify` is a UX hint, not a bypass
    — see AGENTS.md §8.1: appman still checks for a digest/checksum on
    every run regardless of this flag.
    """

    name: str
    repo: str
    default_asset_pattern: str | None = None
    allow_prerelease: bool = False
    allow_skip_verify: bool = False
    architecture: str = "x86_64"


@dataclass(slots=True)
class ReleaseAsset:
    """Raw asset as returned by the GitHub REST API (pre-classification).

    Distinct from `Asset`: this is the wire-shape straight off the API;
    `Asset` is the appman-internal, classified representation produced by
    `parse_asset`. Kept separate so api.py doesn't need to know about
    AssetType classification rules.
    """

    name: str
    download_url: str
    size: int
    content_type: str


@dataclass(slots=True)
class GitHubRelease:
    """A parsed GitHub release, ready for asset-selection (ARCHITECTURE.md §8)."""

    tag_name: str
    release_name: str
    prerelease: bool
    published_at: str
    assets: list[ReleaseAsset] = field(default_factory=list)


@dataclass(slots=True)
class SelectedAssets:
    """Result of the asset-selection pipeline: resolve once, pass around.

    Exists specifically so code doesn't thread the full release asset list
    through every function (AGENTS.md §9). `checksum_file` is None if the
    release has no checksum/.DIGEST asset — that's a normal, expected case,
    not an error.
    """

    appimage: Asset
    checksum_file: Asset | None = None


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    MISSING = "missing"
    SKIPPED = "skipped"


@dataclass(slots=True)
class ChecksumResult:
    """Outcome of verifying one AppImage against digest and/or checksum file.

    `method` distinguishes partial vs. full verification per AGENTS.md §8.2:
    "digest", "checksum_file", or "digest+checksum_file" when both passed.
    """

    status: VerificationStatus
    method: str | None = None
    expected_hash: str | None = None
    actual_hash: str | None = None
    source_file: str | None = None


# ---------------------------------------------------------------------------
# Transaction phase / stage
# ---------------------------------------------------------------------------


class Stage(Enum):
    QUERY = "query"
    DOWNLOAD = "download"
    VERIFY = "verify"
    INSTALL = "install"
    UPDATE = "update"


class Phase(Enum):
    """Internal orchestration phase — coarser-grained than Stage, used for
    progress/event reporting rather than error attribution.
    """

    QUERY = auto()
    DOWNLOAD = auto()
    VERIFY = auto()
    INSTALL = auto()
    SUMMARY = auto()


class Event(Enum):
    """Emitted during install/update for progress reporting (--verbose, TUI)."""

    DOWNLOAD_STARTED = auto()
    DOWNLOAD_FINISHED = auto()
    APPIMAGE_VERIFIED = auto()
    APPIMAGE_VERIFICATION_SKIPPED = auto()
    APPIMAGE_INSTALLED = auto()
    APPIMAGE_FAILED = auto()


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------


class ErrorKind(Enum):
    """Broad category — used for --json grouping and log filtering."""

    NETWORK = "network"
    ASSET = "asset"
    VERIFICATION = "verification"
    PERMISSION = "permission"
    INTERNAL = "internal"


class ErrorCode(Enum):
    """Exact issue. Add a member here + an ERROR_MESSAGES entry when adding
    a new failure mode — never inline a user-facing string elsewhere.
    """

    APPIMAGE_ASSET_NOT_FOUND = "appimage_asset_not_found"
    NETWORK_TIMEOUT = "network_timeout"
    NETWORK_DNS_FAILURE = "network_dns_failure"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    PERMISSION_DENIED = "permission_denied"
    UNKNOWN_ERROR = "unknown_error"


@dataclass(slots=True)
class PackageError:
    """Returned, never raised, across module boundaries (AGENTS.md §6)."""

    package: str
    kind: ErrorKind
    code: ErrorCode
    stage: str
    retryable: bool = False


ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.APPIMAGE_ASSET_NOT_FOUND: (
        "appimage asset not found : appimage builds may still be processing, "
        "try again later. Some developers may not provide appimage builds, "
        "so this might be external to appman's control."
    ),
    ErrorCode.NETWORK_TIMEOUT: "network timeout while downloading asset",
    ErrorCode.NETWORK_DNS_FAILURE: "could not resolve upstream host",
    ErrorCode.PERMISSION_DENIED: "permission denied",
    # Real, parseable mismatch — security-relevant, always blocks by default
    # (AGENTS.md §6.2). Never share this code with CHECKSUM_FILE_CORRUPT.
    ErrorCode.CHECKSUM_MISMATCH: "checksum verification failed",
    ErrorCode.UNKNOWN_ERROR: "an unknown error occurred",
}


# ---------------------------------------------------------------------------
# Typed warnings
# ---------------------------------------------------------------------------


class WarningCode(Enum):
    """Non-fatal issue. Same rule as ErrorCode: add a member + message here,
    don't invent ad hoc strings inline.
    """

    NO_CHECKSUM_SKIPPED = "no_checksum_skipped"
    NO_CHECKSUM_UNSUPPORTED = "no_checksum_unsupported"
    # File present but unparseable/malformed (common with Electron-style
    # build pipelines) — a data-quality problem, NOT a security failure,
    # and must not block install on its own if another method passes.
    CHECKSUM_FILE_CORRUPT = "checksum_file_corrupt"


@dataclass(slots=True)
class PackageWarning:
    package: str
    code: WarningCode
    stage: str


WARNING_MESSAGES: dict[WarningCode, str] = {
    WarningCode.NO_CHECKSUM_SKIPPED: (
        "no checksum provided by upstream : skipping verification"
    ),
    WarningCode.NO_CHECKSUM_UNSUPPORTED: (
        "checksum asset not found : some developers not provide any, please "
        "report an issue for the package maintainers if you verified this "
        "isn't appman's fault"
    ),
    WarningCode.CHECKSUM_FILE_CORRUPT: (
        "checksum file could not be parsed : this is likely an upstream "
        "build-tooling issue, not a verification failure"
    ),
}
