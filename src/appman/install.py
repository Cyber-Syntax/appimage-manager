"""Install orchestration for appman."""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from .api import (
    cache_release_data,
    fetch_latest_release,
    parse_github_url,
    select_appimage_asset,
)
from .constants import APPIMAGES_DIR
from .download import download_and_verify
from .models import (
    INFO_MESSAGES,
    WARNING_MESSAGES,
    ErrorCode,
    ErrorKind,
    InfoCode,
    PackageError,
    PackageWarning,
    SelectedAssets,
    Stage,
)

logger = logging.getLogger(__name__)


# TODO: make sure about the structure for this module
# clean up the code and make sure about the flow of the install process
def _print_package_error(error: PackageError) -> None:
    """Print a structured install failure message."""
    logger.error(
        "%s: %s/%s at %s (retryable=%s)",
        error.package,
        error.kind.value,
        error.code.value,
        error.stage,
        error.retryable,
    )


def _print_package_warning(warning: PackageWarning) -> None:
    """Print a structured install warning message."""
    message = WARNING_MESSAGES.get(warning.code, warning.code.value)
    logger.warning(
        "%s: %s at %s - %s",
        warning.package,
        warning.code.value,
        warning.stage,
        message,
    )


def _exit_with_error(error: PackageError) -> None:
    """Print a package error and terminate the install flow."""
    _print_package_error(error)
    raise SystemExit(1)


# TODO: I probably need to return PackageError instead of raise here:
# FIXME: typeerrors
async def _install_async(url: str) -> None | PackageError:
    """Run the install flow for one GitHub repository URL."""
    try:
        logger.debug("Parsing GitHub URL: %s", url)
        owner, repo = parse_github_url(url)
    except ValueError as exc:
        logger.error(f"appman: {exc}")
        return PackageError(
            package=url,
            kind=ErrorKind.VALIDATION,
            code=ErrorCode.INVALID_URL,
            stage=Stage.QUERY.value,
            retryable=False,
        )

    package = repo

    async with aiohttp.ClientSession(
        headers={"Accept": "application/vnd.github+json"}
    ) as session:
        release = await fetch_latest_release(session, owner, repo, package)
        if isinstance(release, PackageError):
            return release

        cache_release_data(owner, repo, release)

        assets = release.get("assets", [])
        selected_appimage = select_appimage_asset(assets, package)
        if isinstance(selected_appimage, PackageError):
            return selected_appimage

        selected = SelectedAssets(appimage=selected_appimage)

        result = await download_and_verify(
            session=session,
            package=package,
            selected=selected,
            dest_dir=APPIMAGES_DIR,
        )
        if isinstance(result, PackageError):
            return result

        appimage_path, verification, warnings = result

        logger.debug("Downloaded: %s", appimage_path)
        logger.debug("Verification: %s", verification.status.value)

        for warning in warnings:
            _print_package_warning(warning)

        return None  # success


def install(url: str) -> None:
    """Install an AppImage from a GitHub repository URL."""
    logger.info("%s", INFO_MESSAGES[InfoCode.QUERYING_UPSTREAM_RELEASES])
    logger.debug("Installing from URL: %s", url)
    result = asyncio.run(_install_async(url))
    if isinstance(result, PackageError):
        _exit_with_error(result)
