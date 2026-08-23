"""Canonical data models, typed error/warning codes, and message tables.

Every dataclass here is the single source of truth referenced elsewhere
(cli.py, config.py, install.py, update.py, api.py, file_ops.py). If you add
a field, update the JSON state schema examples and config.py migration
logic in the same PR.

Nothing in this module raises. Business-outcome failures are represented
as data (PackageError / PackageWarning), never exceptions, per AGENTS.md §6.

| None → the value may be empty (None).
= None → if you don't provide a value, Python uses None.
NotRequired[...] → the dictionary key itself may be non exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, NotRequired, TypedDict

if TYPE_CHECKING:
    from pathlib import Path

# TODO: refactor google style docstrings


# ---------------------------------------------------------------------------
# Asset classification
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DownloadedAsset:
    """A single asset that has been written to disk.

    Arguments:
        asset: the Asset that was downloaded (Asset)
        path: the path on disk where the asset was written (Path)
    """

    asset: Asset
    path: Path


class AssetType(Enum):
    """Classifies a release asset for appman-internal purposes.

    Arguments:
        APPIMAGE: the asset is an AppImage
        CHECKSUM_FILE: the asset is a checksum file (e.g. .DIGEST.txt)
    """

    APPIMAGE = "AppImage"
    CHECKSUM_FILE = "checksum_file"
    OTHER_TYPE = "other_type"


@dataclass(frozen=True, slots=True)
class Asset:
    """A single raw release asset, parsed from the GitHub API response.

    Arguments:
        name: the name of the asset (e.g. "MyApp-x86_64.AppImage")
        download_url: the URL to download the asset
        size: the size of the asset in bytes
        asset_type: the type of the asset (AppImage or checksum file)
                    (AssetType)
        digest: the SHA256 digest of the asset, if provided by GitHub
                (e.g "sha256:abc123..." -> stored hex-only); None otherwise
    """

    name: str
    download_url: str
    size: int
    asset_type: AssetType
    digest: str | None  # str, present and optional but nullable value


# ---------------------------------------------------------------------------
# Core domain dataclasses # ---------------------------------------------------------------------------


@dataclass(slots=True)
class AppConfig:
    """Per-app persisted config (state JSON), one file per installed app.

    Arguments:
        name: canonical name of the app (used in config file names, etc.)
        repo: GitHub repository (owner/repo)
        installed_version: the version string of the installed AppImage
        appimage_path: path to the installed AppImage
        desktop_file_path: path to the installed .desktop file (if any)
        icon_path: path to the installed icon file (if any)
        skip_verify: whether the user has opted to skip verification
        created_from_catalog: whether this app was installed from the catalog
        catalog_id: the ID of the catalog entry (if any) that was used to install
    """

    name: str
    repo: str
    installed_version: str
    appimage_path: Path
    desktop_file_path: Path | None = (
        None  # either Path or None and default is None
    )
    icon_path: Path | None = None
    skip_verify: bool = False  # bool and default is False
    created_from_catalog: bool = True
    catalog_id: str | None = None


@dataclass(slots=True)
class CatalogEntry:
    """Maintainer-curated override for a catalog app.

    Catalog rules always take precedence over generic GitHub-inferred
    defaults. `allow_skip_verify` is a UX hint that prevents asking the
    same skip verification question to the user every time, not a bypass
    — appman still checks for a digest/checksum on every run regardless
    of this flag.

    Arguments:
        name: canonical name of the app (used in config file names, etc.)
        repo: GitHub repository (owner/repo)
        default_asset_pattern: optional regex pattern to select the AppImage
        allow_prerelease: whether to allow prerelease versions
        allow_skip_verify: whether to allow users to skip verification
        architecture: the architecture of the app (default: x86_64)
    """

    name: str
    repo: str
    default_asset_pattern: str | None = None
    allow_prerelease: bool = False
    allow_skip_verify: bool = False
    architecture: str = "x86_64"


class GitHubAssetPayload(TypedDict):
    """Raw shape of one asset object in the GitHub releases API JSON.

    Arguments:
        name: the name of the asset (e.g. "MyApp-x86_64.AppImage")
        browser_download_url: the URL to download the asset
        size: the size of the asset in bytes
        content_type: the MIME type of the asset (e.g. "application/octet-stream")
        digest: the SHA256 digest of the asset, if provided by GitHub
                (e.g "sha256:abc123..." -> stored hex-only); None otherwise)
    """

    name: str
    browser_download_url: str
    size: int
    content_type: NotRequired[str]  # Optional/missing key
    digest: NotRequired[str | None]  # # Optional/missing key; might be null


class GitHubReleasePayload(TypedDict):
    """Raw shape of a GitHub release object in the GitHub releases API JSON.

    Arguments:
        tag_name: the Git tag name of the release (e.g. "v1.2.3")
        name: the human-readable name of the release (e.g. "MyApp 1.2.3")
        prerelease: whether the release is a prerelease
        published_at: the ISO 8601 timestamp of when the release was published
        assets: a list of asset objects associated with the release
                (GithubAssetPayload)
    """

    tag_name: str
    name: NotRequired[str]  # Optional/missing key
    prerelease: bool
    published_at: str
    assets: list[GitHubAssetPayload]


@dataclass(slots=True)
class ReleaseAsset:
    """Raw asset as returned by the GitHub REST API (pre-classification).

    Distinct from `Asset`: this is the wire-shape straight off the API;
    `Asset` is the appman-internal, classified representation produced by
    `parse_asset`. Kept separate so api.py doesn't need to know about
    AssetType classification rules.

    Arguments:
        name: the name of the asset (e.g. "MyApp-x86_64.AppImage")
        download_url: the URL to download the asset
        size: the size of the asset in bytes
        content_type: the MIME type of the asset (e.g. "application/octet-stream")
        digest: the SHA256 digest of the asset, if provided by GitHub
                (e.g "sha256:abc123..." -> stored hex-only); None otherwise
    """

    name: str
    download_url: str
    size: int
    content_type: str
    digest: str | None = None


@dataclass(slots=True)
class GitHubRelease:
    """A parsed GitHub release, ready for asset-selection.

    Arguments:
        tag_name: the Git tag name of the release (e.g. "v1.2.3")
        release_name: the human-readable name of the release (e.g. "MyApp 1.2.3")
        prerelease: whether the release is a prerelease
        published_at: the ISO 8601 timestamp of when the release was published
        assets: a list of ReleaseAsset objects associated with the release
                (ReleaseAsset)
    """

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

    Arguments:
        appimage: the selected AppImage asset (Asset)
        checksum_file: the selected checksum file asset (Asset) or None if not present
    """

    appimage: Asset
    checksum_file: Asset | None = None


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


class VerificationStatus(Enum):
    """Verification status of an AppImage against digest and/or checksum file.

    Arguments:
        VERIFIED: the AppImage was successfully verified
        FAILED: the AppImage failed verification
        MISSING: the AppImage could not be verified because the checksum file
                 or digest was missing
        SKIPPED: the AppImage verification was skipped (user opted out)
    """

    VERIFIED = "verified"
    FAILED = "failed"
    MISSING = "missing"
    SKIPPED = "skipped"


@dataclass(slots=True)
class ChecksumResult:
    """Outcome of verifying one AppImage against digest and/or checksum file.

    `method` distinguishes partial vs. full verification per
    "digest", "checksum_file", or "digest+checksum_file" when both passed.

    Arguments:
        status: the verification status (VERIFIED, FAILED, MISSING, SKIPPED)
                (VerificationStatus)
        method: the method used for verification (digest, checksum_file, or both)
        expected_hash: the expected hash value (from digest or checksum file)
        actual_hash: the actual hash value computed from the downloaded AppImage
        source_file: the source of the expected hash (digest or checksum file)
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
    """Internal orchestration stage.

    Stages are used for fine-grained progress reporting and logging.

    Arguments:
        QUERY: querying upstream releases
        DOWNLOAD: downloading assets
        VERIFY: verifying downloaded assets
        INSTALL: installing assets
        UPDATE: updating installed assets
    """

    QUERY = "query"
    DOWNLOAD = "download"
    VERIFY = "verify"
    INSTALL = "install"
    UPDATE = "update"


class Phase(Enum):
    """Internal orchestration phase.

    Phases are used for higher-level progress reporting and logging.

    Arguments:
        QUERY: querying upstream releases
        DOWNLOAD: downloading assets
        VERIFY: verifying downloaded assets
        INSTALL: installing assets
        SUMMARY: summarizing the transaction
    """

    QUERY = auto()
    DOWNLOAD = auto()
    VERIFY = auto()
    INSTALL = auto()
    SUMMARY = auto()


class Event(Enum):
    """Emitted during install/update for progress reporting (--verbose, TUI).

    Arguments:
        DOWNLOAD_STARTED: download of an asset has started
        DOWNLOAD_FINISHED: download of an asset has finished
        APPIMAGE_VERIFIED: AppImage has been successfully verified
        APPIMAGE_VERIFICATION_SKIPPED: AppImage verification was skipped
        APPIMAGE_INSTALLED: AppImage has been successfully installed
        APPIMAGE_FAILED: AppImage installation failed
    """

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
    """Broad category — used for --json grouping and log filtering.

    Arguments:
        NETWORK: network-related errors (timeouts, DNS failures)
        ASSET: asset-related errors (missing, malformed, etc.)
        VERIFICATION: verification-related errors (checksum mismatches, etc.)
        PERMISSION: permission-related errors (file system, access denied)
        INTERNAL: internal errors (unexpected exceptions, logic errors)
        VALIDATION: validation errors (invalid input, unsupported URLs)
    """

    NETWORK = "network"
    ASSET = "asset"
    VERIFICATION = "verification"
    PERMISSION = "permission"
    INTERNAL = "internal"
    VALIDATION = "validation"


class ErrorCode(Enum):
    """Error codes are used for structured error reporting and logging.

    Arguments:
        APPIMAGE_ASSET_NOT_FOUND: the AppImage asset was not found in the release
        NETWORK_TIMEOUT: a network timeout occurred while downloading an asset
        NETWORK_DNS_FAILURE: DNS resolution failed for the upstream host
        CHECKSUM_MISMATCH: the checksum verification failed for the downloaded asset
        PERMISSION_DENIED: permission denied when accessing a file or directory
        INVALID_URL: the provided repository URL is invalid or unsupported
        UNKNOWN_ERROR: an unknown error occurred
    """

    APPIMAGE_ASSET_NOT_FOUND = "appimage_asset_not_found"
    NETWORK_TIMEOUT = "network_timeout"
    NETWORK_DNS_FAILURE = "network_dns_failure"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    PERMISSION_DENIED = "permission_denied"
    INVALID_URL = "invalid_url"
    MALFORMED_RESPONSE = "malformed_response"
    UNKNOWN_ERROR = "unknown_error"


@dataclass(slots=True)
class PackageError:
    """Returned, never raised, across module boundaries.

    Arguments:
        package: the name of the package that encountered the error
        kind: the broad category of the error (ErrorKind)
        code: the specific error code (ErrorCode)
        stage: the stage of the transaction where the error occurred (Stage)
        retryable: whether the error is retryable (default: False)
    """

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
    # Never share this code with CHECKSUM_FILE_CORRUPT.
    ErrorCode.CHECKSUM_MISMATCH: "checksum verification failed",
    ErrorCode.INVALID_URL: (
        "invalid or unsupported repository URL: expected GitHub URL. "
        "Example: https://github.com/pbek/QOwnNotes"
    ),
    ErrorCode.MALFORMED_RESPONSE: "Malformed release payload",
    ErrorCode.UNKNOWN_ERROR: "an unknown error occurred",
}


# ---------------------------------------------------------------------------
# Typed warnings
# ---------------------------------------------------------------------------


class WarningCode(Enum):
    """Warning codes are used for structured warning reporting and logging.

    Note:
        File present but unparseable/malformed (common with Electron-style
        build pipelines) — a data-quality problem, NOT a security failure,
        and must not block install on its own if another method passes.

    Arguments:
        NO_CHECKSUM_SKIPPED: no checksum was provided by upstream,
                             skipping verification
        NO_CHECKSUM_UNSUPPORTED: checksum asset not found, some developers
                                 may not provide any
        CHECKSUM_FILE_CORRUPT: checksum file could not be parsed,
                               likely an upstream build-tooling issue,
                               not a verification failure
        UNKNOWN_WARNING: an unknown warning occurred
    """

    NO_CHECKSUM_SKIPPED = "no_checksum_skipped"
    NO_CHECKSUM_UNSUPPORTED = "no_checksum_unsupported"
    CHECKSUM_FILE_CORRUPT = "checksum_file_corrupt"
    DUPLICATE_TARGET_SKIPPED = "duplicate_target_skipped"
    UNKNOWN_WARNING = "unknown_warning"


@dataclass(slots=True)
class PackageWarning:
    """Returned, never raised, across module boundaries.

    Arguments:
        package: the name of the package that encountered the warning
        code: the specific warning code (WarningCode)
        stage: the stage of the transaction where the warning occurred (Stage)
    """

    package: str
    code: WarningCode
    stage: str


WARNING_MESSAGES: dict[WarningCode, str] = {
    WarningCode.NO_CHECKSUM_SKIPPED: (
        "no checksum provided by upstream : skipping verification"
    ),
    WarningCode.NO_CHECKSUM_UNSUPPORTED: (
        "checksum asset not found : some developers do not provide any, please "
        "report an issue for the package maintainers if you verified this "
        "isn't appman's fault"
    ),
    WarningCode.CHECKSUM_FILE_CORRUPT: (
        "checksum file could not be parsed : this is likely an upstream "
        "build-tooling issue, not a verification failure"
    ),
    WarningCode.DUPLICATE_TARGET_SKIPPED: (
        "duplicate install target skipped : same repository was already "
        "queued in this transaction"
    ),
    WarningCode.UNKNOWN_WARNING: "an unknown warning occurred",
}


# ----------------------------------------------------------------------------
# Typed infos
# ----------------------------------------------------------------------------


class InfoCode(Enum):
    """Info codes are used for structured info reporting and logging.

    Arguments:
        QUERYING_UPSTREAM_RELEASES: querying upstream releases
        RETRIEVING_APPIMAGES: retrieving appimages
        PROCESSING_PACKAGE_CHANGES: processing package changes
        CREATING_TRANSACTION_SUMMARY: creating transaction summary
        DONE: done
    """

    QUERYING_UPSTREAM_RELEASES = "querying_upstream_releases"
    RETRIEVING_APPIMAGES = "retrieving_appimages"
    PROCESSING_PACKAGE_CHANGES = "processing_package_changes"
    CREATING_TRANSACTION_SUMMARY = "creating_transaction_summary"
    DONE = "done"


INFO_MESSAGES: dict[InfoCode, str] = {
    InfoCode.QUERYING_UPSTREAM_RELEASES: ":: Querying upstream releases...",
    InfoCode.RETRIEVING_APPIMAGES: ":: Retrieving appimages...",
    InfoCode.PROCESSING_PACKAGE_CHANGES: ":: Processing package changes...",
    InfoCode.CREATING_TRANSACTION_SUMMARY: ":: Creating transaction summary...",
    InfoCode.DONE: ":: Done.",
}
