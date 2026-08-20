"""Utilities for interacting with the GitHub API."""

import logging
import re
from typing import cast

import aiohttp
import orjson

from .constants import (
    API_SEMAPHORE,
    CACHE_DIR,
    HTTP_404,
    INCOMPATIBLE_PLATFORM_EXTENSIONS,
    INCOMPATIBLE_PLATFORM_PATTERNS,
    UNSTABLE_VERSION_KEYWORDS,
)
from .models import (
    Asset,
    AssetType,
    ErrorCode,
    ErrorKind,
    GitHubAssetPayload,
    GitHubRelease,
    GitHubReleasePayload,
    PackageError,
    ReleaseAsset,
    SelectedAssets,
    Stage,
)

logger = logging.getLogger(__name__)

_CHECKSUM_EXTENSIONS = (
    ".sha256sum",
    ".sha256",
    ".sha512sum",
    ".sha512",
    ".digest",
    ".yml",
    ".yaml",
)

_CHECKSUM_EXACT_NAMES = frozenset(
    {
        "sha256sums",
        "sha256sums.txt",
        "sha512sums",
        "sha512sums.txt",
        "checksums",
        "checksums.txt",
    }
)

# Release-wide manifests that verify every asset in the release rather than
# one specific file (e.g. electron-builder's latest-linux.yml, or a single
# SHA256SUMS covering all binaries). Used as a fallback when no per-file
# checksum matches the selected AppImage by name.
_RELEASE_WIDE_CHECKSUM_NAMES = frozenset(
    {
        "sha256sums",
        "sha256sums.txt",
        "sha512sums",
        "sha512sums.txt",
        "checksums",
        "checksums.txt",
        "latest-linux.yml",
        "latest.yml",
    }
)

# INCOMPATIBLE_PLATFORM_EXTENSIONS (.msi/.exe/.dmg/.pkg) can appear anywhere
# in a filename, not just as the true suffix — e.g. "app-x86_64.dmg.DIGEST"
# ends in ".DIGEST", not ".dmg". Match the extension embedded anywhere,
# bounded by a separator or end-of-string, so it still doesn't false-positive
# on something like "app-dmgsomething.AppImage".
_EMBEDDED_INCOMPATIBLE_EXT_RE = re.compile(
    r"(?:{})(?:[._-]|$)".format(
        "|".join(re.escape(ext) for ext in INCOMPATIBLE_PLATFORM_EXTENSIONS)
    )
)


# TODO: make it case-insensitive
def parse_github_url(url: str) -> tuple[str, str] | PackageError:
    """Extract the repository owner and name from a GitHub URL.

    Args:
        url: The GitHub repository URL.

    Returns:
        tuple: A tuple containing the owner and repository name if successful.
        PackageError: If the URL is invalid or unsupported.
    """
    # Regex pattern to capture owner and repo
    # Handles: https://github.com/owner/repo | https://github.com/owner/repo.git
    # | git@github.com:owner/repo.git
    pattern = r"(?:https?://github\.com/|git@github\.com:)(?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?"

    logger.debug("Parsing GitHub URL: %s", url)
    match = re.search(pattern, url)
    if not match:
        return PackageError(
            package=url,
            kind=ErrorKind.VALIDATION,
            code=ErrorCode.INVALID_URL,
            stage=Stage.QUERY.value,
            retryable=False,
        )

    return match.group("owner"), match.group("repo")


# TODO: add expection for malformed JSON body
async def fetch_latest_release(
    session: aiohttp.ClientSession,
    owner: str,
    repo: str,
    package: str,
) -> GitHubRelease | PackageError:
    """Fetch latest release from github.

    Args:
        session: The aiohttp session to use for the request.
        owner: The owner of the GitHub repository.
        repo: The name of the GitHub repository.
        package: The package name for error reporting.

    Returns:
        GitHubRelease: The latest release data if successful.
        PackageError: If an error occurs during the fetch.
    """
    logger.debug("Fetching latest release for %s/%s", owner, repo)
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    # Use a semaphore to limit concurrent API requests because of rate limits.
    async with API_SEMAPHORE:
        try:
            # NOTE: session.get() doesn't fetch anything by itself
            # enterin "async with" is what actually send the request
            # and pauses this task until the response HEADERS come back.
            # Other tasks run while we wait here.
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                logger.debug("Received response: %s", response)
                if response.status == HTTP_404:
                    return PackageError(
                        package=package,
                        kind=ErrorKind.ASSET,
                        code=ErrorCode.APPIMAGE_ASSET_NOT_FOUND,
                        stage=Stage.QUERY.value,
                        retryable=True,
                    )
                response.raise_for_status()
                # NOTE: aiohttp.json is typed Any - this is the one deliberate
                # boundry crossing. Parse into GitHubRelease immediately
                # so Any never escapes this function.
                #
                # NOTE: headers arrived above, but the response body still
                # needs to be downloaded and parsed as JSON. That's a second,
                # seperate wait. "await response.json()" pauses this task
                # again until the whole body has arrived and been parsed.
                raw = cast("GitHubReleasePayload", await response.json())
                logger.debug("Raw release data: %s", raw)
                cache_release_data(owner, repo, raw)
                return _parse_release_data(raw)
        except aiohttp.ClientConnectorError:
            return PackageError(
                package=package,
                kind=ErrorKind.NETWORK,
                code=ErrorCode.NETWORK_DNS_FAILURE,
                stage=Stage.QUERY.value,
                retryable=True,
            )
        except (TimeoutError, aiohttp.ClientError):
            return PackageError(
                package=package,
                kind=ErrorKind.NETWORK,
                code=ErrorCode.NETWORK_TIMEOUT,
                stage=Stage.QUERY.value,
                retryable=True,
            )


def _parse_release_data(raw: GitHubReleasePayload) -> GitHubRelease:
    """Parse raw GitHub release data into a GitHubRelease object.

    Args:
        raw: The raw release data from the GitHub API.

    Returns:
        GitHubRelease: The parsed release data.
    """
    return GitHubRelease(
        tag_name=raw["tag_name"],
        release_name=raw.get("name") or raw["tag_name"],
        prerelease=raw["prerelease"],
        published_at=raw["published_at"],
        assets=[_parse_release_asset(a) for a in raw.get("assets", [])],
    )


def _parse_release_asset(raw: GitHubAssetPayload) -> ReleaseAsset:
    """Parse raw GitHub release asset data into a ReleaseAsset object.

    Args:
        raw: The raw asset data from the GitHub API.

    Returns:
        The parsed ReleaseAsset object, with digest normalized to
        hex-only (the "sha256:" prefix is stripped if present).
    """
    raw_digest = raw.get("digest")  # e.g "sha256:abc123..."
    digest = raw_digest.split(":", 1)[1] if raw_digest else None
    return ReleaseAsset(
        name=raw["name"],
        download_url=raw["browser_download_url"],
        size=raw["size"],
        content_type=raw.get("content_type", ""),
        digest=digest,
    )


# TODO: use cache for later retry or same app version install
# if something fail we can retry to install same than we could use cache directly
# to get the browser_download_url etc. from that raw returned json file in that cache json
def cache_release_data(
    owner: str, repo: str, data: GitHubReleasePayload
) -> None:
    """Cache the latest release data for a GitHub repository.

    Args:
        owner: The owner of the GitHub repository.
        repo: The name of the GitHub repository.
        data: The release data to cache.

    Returns:
        None
    """
    cache_path = CACHE_DIR / f"{owner}_{repo}_latest.json"

    with cache_path.open("wb") as file:
        _ = file.write(orjson.dumps(data))
    logger.debug("Cached release data to: %s", cache_path)


def select_appimage_asset(
    assets: list[ReleaseAsset], package: str
) -> SelectedAssets | PackageError:
    """Select the best AppImage asset and its matching checksum/digest file.

    Per ARCHITECTURE.md §8 ("retain associated checksum asset if present"),
    this now resolves both halves of verification in one pass instead of
    discarding checksum assets: the AppImage is chosen first (platform
    filter → stable-over-beta, unless every candidate is unstable, e.g.
    FreeTube → prefer amd64/x86_64), then a matching checksum file is
    resolved against that specific AppImage.

    Arguments:
        assets: The list of raw asset dictionaries from the GitHub API.
        package: The package name for error reporting.

    Returns:
        SelectedAssets: The best AppImage asset, with its checksum file
            if one was found (None is a normal, expected outcome, not
            an error — many upstreams simply don't ship one).
        PackageError: If no suitable AppImage is found.
    """
    logger.debug("Selecting AppImage asset from %d assets", len(assets))
    parsed = [parse_asset(raw) for raw in assets]

    appimage = _select_best_appimage(parsed, package)
    if isinstance(appimage, PackageError):
        return appimage

    checksum_file = _select_matching_checksum_file(parsed, appimage)
    logger.debug(
        "Selected AppImage: %s, checksum file: %s",
        appimage.name,
        checksum_file.name if checksum_file else None,
    )
    return SelectedAssets(appimage=appimage, checksum_file=checksum_file)


def _select_best_appimage(
    parsed: list[Asset], package: str
) -> Asset | PackageError:
    """Run the appimage-only selection pipeline (platform -> stability -> arch.

    Arguments:
        parsed: The full list of classified assets from the release.
        package: The package name for error reporting.

    Returns:
        Asset: The best-matching AppImage asset.
        PackageError: If no suitable AppImage is found.
    """
    appimages = [a for a in parsed if a.asset_type == AssetType.APPIMAGE]
    matches = [a for a in appimages if not is_incompatible_platform(a.name)]
    logger.debug("Found %d match AppImage assets", len(matches))

    if not matches:
        return PackageError(
            package=package,
            kind=ErrorKind.ASSET,
            code=ErrorCode.APPIMAGE_ASSET_NOT_FOUND,
            stage=Stage.QUERY.value,
            retryable=True,
        )

    stable = [a for a in matches if not is_unstable(a.name)]
    # keep all beta apps to support freetube and similar always beta apps
    matches = stable or matches
    logger.debug("Final match AppImage assets: %d", len(matches))

    return next(
        (a for a in matches if is_amd64(a.name)),
        matches[0],
    )


def _select_matching_checksum_file(
    parsed: list[Asset], appimage: Asset
) -> Asset | None:
    """Find the checksum/digest asset that verifies the selected AppImage.

    Real-world checksum files come in two shapes:
      1. Per-file: named after the AppImage itself, e.g.
         "QOwnNotes-x86_64.AppImage.sha256sum" for
         "QOwnNotes-x86_64.AppImage" — matched by prefix.
      2. Release-wide manifests covering every asset in the release, e.g.
         "SHA256SUMS" or "latest-linux.yml" — used only as a fallback
         when no per-file match exists.
    Platform-incompatible checksum files (e.g. a stray macOS/Windows
    counterpart) are filtered out the same way AppImages are, so a
    "KeePassXC-2.7.10-x86_64.dmg.DIGEST" is never mistaken for a match
    despite containing "x86_64".

    Arguments:
        parsed: The full list of classified assets from the release.
        appimage: The AppImage asset already selected.

    Returns:
        The matching checksum Asset, or None if the release has no
        usable checksum/digest file — a normal, expected outcome.
    """
    candidates = [
        a
        for a in parsed
        if a.asset_type == AssetType.CHECKSUM_FILE
        and not is_incompatible_platform(a.name)
    ]
    # TODO: might be need to return PackageError?
    if not candidates:
        return None

    per_file = next(
        (
            c
            for c in candidates
            if c.name.lower().startswith(appimage.name.lower())
        ),
        None,
    )
    if per_file is not None:
        return per_file

    return next(
        (
            c
            for c in candidates
            if c.name.lower() in _RELEASE_WIDE_CHECKSUM_NAMES
        ),
        None,
    )


def parse_asset(raw: ReleaseAsset) -> Asset:
    """Convert a raw GitHub API asset dict into an Asset.

    Arguments:
        raw: The raw asset dictionary from the GitHub API.

    Returns:
        The parsed Asset object.
    """
    logger.debug("Parsed asset: %s, digest: %s", raw.name, raw.digest)
    return Asset(
        name=raw.name,
        download_url=raw.download_url,
        size=raw.size,
        asset_type=classify_asset_type(raw.name),
        digest=raw.digest,
    )


def classify_asset_type(name: str) -> AssetType:
    """Classify a filename as AppImage, checksum file, or digest.

    Checksum files are recognized by known extensions (.sha256sum,
    .DIGEST, .yml, ...) or exact release-wide manifest names
    (SHA256SUMS, SHA256SUMS.txt, ...)

    Arguments:
        name: The name of the filename to classify.

    Returns:
        The type of the asset:
            APPIMAGE
            CHECKSUM_FILE
            OTHER_TYPE
    """
    lower = name.lower()
    if lower.endswith(".appimage"):
        return AssetType.APPIMAGE
    if lower.endswith(_CHECKSUM_EXTENSIONS) or lower in _CHECKSUM_EXACT_NAMES:
        return AssetType.CHECKSUM_FILE
    return AssetType.OTHER_TYPE


def is_incompatible_platform(name: str) -> bool:
    """Check if the asset name indicates an incompatible platform.

    Checks both true-suffix extensions (app.dmg) and extensions embedded
    earlier in a compound filename (app-x86_64.dmg.DIGEST — a macOS
    checksum file whose *true* suffix is .DIGEST), then falls back to the
    existing win/mac/arm keyword patterns.

    Arguments:
        name: The name of the asset.

    Returns:
        True if the asset is incompatible with the current platform,
        False otherwise.
    """
    lower = name.lower()
    if _EMBEDDED_INCOMPATIBLE_EXT_RE.search(lower):
        return True
    return any(
        re.search(pattern, lower) for pattern in INCOMPATIBLE_PLATFORM_PATTERNS
    )


def is_unstable(name: str) -> bool:
    """Check if the asset name indicates an unstable version.

    Arguments:
        name: The name of the asset.

    Returns:
        True if the asset indicates an unstable version, False otherwise.
    """
    lower = name.lower()
    return any(kw in lower for kw in UNSTABLE_VERSION_KEYWORDS)


def is_amd64(name: str) -> bool:
    """Check if the asset name indicates an AMD64 platform.

    Arguments:
        name: The name of the asset.

    Returns:
        True if the asset indicates an AMD64 platform, False otherwise.
    """
    lower = name.lower()
    return "x86_64" in lower or "amd64" in lower
