"""Utilities for interacting with the GitHub API."""

import re
from typing import Any

import aiohttp
import orjson

from .constants import (
    API_SEMAPHORE,
    CACHE_DIR,
    INCOMPATIBLE_PLATFORM_EXTENSIONS,
    INCOMPATIBLE_PLATFORM_PATTERNS,
    UNSTABLE_VERSION_KEYWORDS,
)
from .models import Asset, AssetType, ErrorCode, ErrorKind, PackageError, Stage


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


async def fetch_latest_release(
    session: aiohttp.ClientSession, owner: str, repo: str, package: str
) -> dict[str, Any] | PackageError:
    """Fetch latest release from github."""
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    async with API_SEMAPHORE:
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status == 404:
                    return PackageError(
                        package=package,
                        kind=ErrorKind.ASSET,
                        code=ErrorCode.APPIMAGE_ASSET_NOT_FOUND,
                        stage=Stage.QUERY.value,
                        retryable=True,
                    )
                response.raise_for_status()
                return await response.json()
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


# 5. save it to the cache while still on memory
# keep using memory but cache might be needed on later usage for same app install
# e.g if something fail we can retry to install same than we could use cache directly
# to get the browser_download_url etc. from that raw returned json file in that cache json
def cache_release_data(owner: str, repo: str, data: dict[str, Any]) -> None:
    cache_path = CACHE_DIR / f"{owner}_{repo}_latest.json"

    with cache_path.open("wb") as file:
        file.write(orjson.dumps(data))


def select_appimage_asset(
    assets: list[dict[str, Any]], package: str
) -> Asset | PackageError:
    """Find the best AppImage asset from a GitHub release's raw asset list."""
    parsed = [parse_asset(raw) for raw in assets]
    appimages = [
        appimage
        for appimage in parsed
        if appimage.asset_type == AssetType.APPIMAGE
    ]
    candidates = [
        appimage
        for appimage in appimages
        if not is_incompatible_platform(appimage.name)
    ]

    # TODO: might be better to return useful error from known text?
    if not candidates:
        return PackageError(
            package=package,
            kind=ErrorKind.ASSET,
            code=ErrorCode.APPIMAGE_ASSET_NOT_FOUND,
            stage=Stage.QUERY.value,
            retryable=True,
        )

    stable = [
        appimage for appimage in candidates if not is_unstable(appimage.name)
    ]
    # keep all-beta apps to support freetube and similar always beta apps
    candidates = stable or candidates

    return next(
        (appimage for appimage in candidates if is_amd64(appimage.name)),
        candidates[0],
    )


# TODO: we probably need to use this function to
# parse browser_download_url for appimage
# and checksum_file and than use those to download
# both and than verify
def parse_asset(raw: dict[str, Any]) -> Asset:
    """Convert a raw GitHub API asset dict into an Asset."""
    name = raw["name"]
    raw_digest = raw.get("digest")  # e.g "sha256:abc123..."
    # get the digest only, not sha256
    digest = raw_digest.split(":", 1)[1] if raw_digest else None
    return Asset(
        name=name,
        download_url=raw["browser_download_url"],
        size=raw["size"],
        asset_type=classify_asset_type(name),
        digest=digest,
    )


def classify_asset_type(name: str) -> AssetType:
    """Classify a filename as AppImage, checksum file, or digest."""
    lower = name.lower()
    if lower.endswith(".appimage"):
        return AssetType.APPIMAGE
    return AssetType.CHECKSUM_FILE


# TODO: add google-style docstrings and comments for this functions
def is_incompatible_platform(name: str) -> bool:
    lower = name.lower()
    if lower.endswith(INCOMPATIBLE_PLATFORM_EXTENSIONS):
        return True
    return any(
        re.search(pattern, lower) for pattern in INCOMPATIBLE_PLATFORM_PATTERNS
    )


def is_unstable(name: str) -> bool:
    lower = name.lower()
    return any(kw in lower for kw in UNSTABLE_VERSION_KEYWORDS)


def is_amd64(name: str) -> bool:
    lower = name.lower()
    return "x86_64" in lower or "amd64" in lower
