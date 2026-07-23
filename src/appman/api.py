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
    Stage,
)

logger = logging.getLogger(__name__)


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

    async with API_SEMAPHORE:
        try:
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
                # aiohttp.json is typed Any - this is the one deliberate
                # boundry crossing. Parse into GitHubRelease immediately
                # so Any never escapes this function.
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
) -> Asset | PackageError:
    """Find the best AppImage asset from a GitHub release's raw asset list.

    Args:
        assets: The list of raw asset dictionaries from the GitHub API.
        package: The package name for error reporting.

    Returns:
        Asset: The best AppImage asset.
        PackageError: If no suitable AppImage is found.
    """
    logger.debug("Selecting AppImage asset from %d assets", len(assets))
    parsed = [parse_asset(raw) for raw in assets]
    appimages = [
        appimage
        for appimage in parsed
        if appimage.asset_type == AssetType.APPIMAGE
    ]
    matches = [
        appimage
        for appimage in appimages
        if not is_incompatible_platform(appimage.name)
    ]
    logger.debug("Found %d match AppImage assets", len(matches))

    if not matches:
        return PackageError(
            package=package,
            kind=ErrorKind.ASSET,
            code=ErrorCode.APPIMAGE_ASSET_NOT_FOUND,
            stage=Stage.QUERY.value,
            retryable=True,
        )

    stable = [
        appimage for appimage in matches if not is_unstable(appimage.name)
    ]
    # keep all-beta apps to support freetube and similar always beta apps
    matches = stable or matches

    logger.debug("Final match AppImage assets: %d", len(matches))

    return next(
        (appimage for appimage in matches if is_amd64(appimage.name)),
        matches[0],
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

    Arguments:
        name: The name of the filename to classify.

    Returns:
        The type of the asset.
    """
    lower = name.lower()
    if lower.endswith(".appimage"):
        return AssetType.APPIMAGE
    return AssetType.CHECKSUM_FILE


def is_incompatible_platform(name: str) -> bool:
    """Check if the asset name indicates an incompatible platform.

    Arguments:
        name: The name of the asset.

    Returns:
        True if the asset is incompatible with the current platform,
        False otherwise.
    """
    lower = name.lower()
    if lower.endswith(INCOMPATIBLE_PLATFORM_EXTENSIONS):
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
