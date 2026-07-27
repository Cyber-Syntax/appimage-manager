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


async def _install_one(
    session: aiohttp.ClientSession, url: str
) -> tuple[str, str | PackageError]:
    """Run the install flow for one GitHub repository URL.

    Args:
        session: The aiohttp.ClientSession to use for HTTP requests.
        url: The GitHub repository URL to install from.

    Returns:
        tuple: (package name, installed version string) on success.
        tuple: (package name, PackageError) on failure.
    """
    logger.debug("Starting async install flow for URL: %s", url)
    parse_result = parse_github_url(url)
    if isinstance(parse_result, PackageError):
        # no owner/repo yet, use the raw url as the reported "package"
        return parse_result.package, parse_result

    owner, repo = parse_result
    package = repo
    logger.debug("Parsed GitHub URL: owner=%s, repo=%s", owner, repo)

    release = await fetch_latest_release(session, owner, repo, package)
    if isinstance(release, PackageError):
        return package, release

    selected_appimage = select_appimage_asset(release.assets, package)
    if isinstance(selected_appimage, PackageError):
        return package, selected_appimage

    selected = SelectedAssets(appimage=selected_appimage)
    logger.debug(
        "Selected AppImage asset: name=%s",
        selected.appimage.name,
    )

    result = await download_and_verify(
        session=session,
        package=package,
        selected=selected,
        dest_dir=APPIMAGES_DIR,
    )
    if isinstance(result, PackageError):
        return package, result

    appimage_path, _, warnings = result
    logger.debug("Downloaded: %s", appimage_path)

    for warning in warnings:
        _print_package_warning(warning)

    return package, release.tag_name  # success


async def _install_all_async(
    urls: list[str],
) -> list[tuple[str, str | PackageError]]:
    """Run the install flow for multiple GitHub repository URLs concurrently.

    A signle shared session is used for the whole batch and actual
    concurrency is still bounded by API_SEMAPHORE and DOWNLOAD_SEMAPHORE,
    both module-level, so this doesn't bypass those limits.

    Args:
        urls: A list of GitHub repository URLs to install from.

    Returns:
        A list of tuples containing the package name and either the installed
        version string or a PackageError for each URL.
    """
    async with aiohttp.ClientSession() as session:
        tasks = [
            asyncio.ensure_future(_install_one(session, url)) for url in urls
        ]
        return await asyncio.gather(*tasks)


def install(urls: list[str]) -> None:
    """Install one or more AppImages from GitHub repository URLs.

    Valid targets are processed even if others fail.
    Each failure is reported individually and a transaction summary
    is printed regardless of success or failure.

    Exit codes:
        0: all targets installed successfully
        1: partial or total failure (one or more targets failed)

    Args:
        urls: The GitHub repository URLs to install from.

    Returns:
        None

    Raises:
        SystemExit: Raised with exit code 0, 1, or 2.
    """
    logger.info("%s", INFO_MESSAGES[InfoCode.QUERYING_UPSTREAM_RELEASES])
    logger.debug("Starting install command for URL: %s", urls)

    results = asyncio.run(_install_all_async(urls))

    installed: list[tuple[str, str]] = []
    failed: list[tuple[str, PackageError]] = []
    for package, outcome in results:
        if isinstance(outcome, PackageError):
            failed.append((package, outcome))
        else:
            installed.append((package, outcome))

    logger.info("%s", INFO_MESSAGES[InfoCode.CREATING_TRANSACTION_SUMMARY])
    for name, version in installed:
        logger.info("INSTALLED %s %s", name, version)
    for name, _ in failed:
        logger.error("FAILED %s", name)
    logger.info("%s", INFO_MESSAGES[InfoCode.DONE])

    logger.debug(
        "Install command completed with %d successes and %d failures",
        len(installed),
        len(failed),
    )

    if failed:
        raise SystemExit(1)  # partial or total failure
    # all succeeded -> return None, exit 0
