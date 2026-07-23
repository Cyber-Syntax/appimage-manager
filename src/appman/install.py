"""Install orchestration for appman."""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from .api import fetch_latest_release, parse_github_url, select_appimage_asset
from .constants import APPIMAGES_DIR
from .download import download_and_verify
from .models import (
    INFO_MESSAGES,
    WARNING_MESSAGES,
    InfoCode,
    PackageError,
    PackageWarning,
    SelectedAssets,
)

logger = logging.getLogger(__name__)


def _print_package_error(error: PackageError) -> None:
    """Print a structured install failure message.

    Args:
        error: The package error to print.

    Returns:
        None
    """
    logger.error(
        "%s: %s/%s at %s (retryable=%s)",
        error.package,
        error.kind.value,
        error.code.value,
        error.stage,
        error.retryable,
    )


def _print_package_warning(warning: PackageWarning) -> None:
    """Print a structured install warning message.

    Args:
        warning: The package warning to print.

    Returns:
        None
    """
    message = WARNING_MESSAGES.get(warning.code, warning.code.value)
    logger.warning(
        "%s: %s at %s - %s",
        warning.package,
        warning.code.value,
        warning.stage,
        message,
    )


def _exit_with_error(error: PackageError) -> None:
    """Print a package error and terminate the install flow.

    Args:
        error: The package error to print.

    Raises:
        SystemExit: Always raised to terminate the install flow.

    Returns:
        None
    """
    _print_package_error(error)
    raise SystemExit(1)


async def _install_async(url: str) -> None | PackageError:
    """Run the install flow for one GitHub repository URL.

    Args:
        url: The GitHub repository URL to install from.

    Returns:
        None if the installation is successful,
        PackageError if an error occurs.
    """
    logger.debug("Starting async install flow for URL: %s", url)
    parse_result = parse_github_url(url)
    if isinstance(parse_result, PackageError):
        return parse_result

    owner, repo = parse_result
    package = repo
    logger.debug("Parsed GitHub URL: owner=%s, repo=%s", owner, repo)

    # NOTE: Using aiohttp.ClientSession to manage HTTP requests and responses
    # this allows for efficient handling of multiple requests and responses,
    # as well as connection pooling and session management.
    async with aiohttp.ClientSession(
        headers={"Accept": "application/vnd.github+json"}
    ) as session:
        release = await fetch_latest_release(session, owner, repo, package)
        if isinstance(release, PackageError):
            return release

        assets = release.assets
        selected_appimage = select_appimage_asset(assets, package)
        if isinstance(selected_appimage, PackageError):
            return selected_appimage

        selected = SelectedAssets(appimage=selected_appimage)
        logger.debug("Selected AppImage: %s", selected.appimage.name)
        logger.debug("Selected assets: %s", selected)
        result = await download_and_verify(
            session=session,
            package=package,
            selected=selected,
            dest_dir=APPIMAGES_DIR,
        )
        if isinstance(result, PackageError):
            return result

        appimage_path, _, warnings = result
        logger.debug("Downloaded: %s", appimage_path)

        for warning in warnings:
            _print_package_warning(warning)

        return None  # success


def install(url: str) -> None:
    """Install an AppImage from a GitHub repository URL.

    Args:
        url: The GitHub repository URL to install from.

    Returns:
        None
    """
    logger.info("%s", INFO_MESSAGES[InfoCode.QUERYING_UPSTREAM_RELEASES])
    logger.debug("Starting install command for URL: %s", url)
    result = asyncio.run(_install_async(url))
    if isinstance(result, PackageError):
        _exit_with_error(result)

    logger.debug("Install command completed successfully for URL: %s", url)
