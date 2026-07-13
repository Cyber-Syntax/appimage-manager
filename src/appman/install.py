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
from .main import init_config
from .models import (
    WARNING_MESSAGES,
    PackageError,
    PackageWarning,
    SelectedAssets,
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
async def _install_async(url: str) -> None:
    """Run the install flow for one GitHub repository URL."""
    try:
        owner, repo = parse_github_url(url)
    except ValueError as exc:
        logger.error(f"appman: {exc}")
        raise SystemExit(1) from exc

    package = repo

    async with aiohttp.ClientSession(
        headers={"Accept": "application/vnd.github+json"}
    ) as session:
        release = await fetch_latest_release(session, owner, repo, package)
        if isinstance(release, PackageError):
            _exit_with_error(release)

        cache_release_data(owner, repo, release)

        assets = release.get("assets", [])
        selected_appimage = select_appimage_asset(assets, package)
        if isinstance(selected_appimage, PackageError):
            _exit_with_error(selected_appimage)

        selected = SelectedAssets(appimage=selected_appimage)

        result = await download_and_verify(
            session=session,
            package=package,
            selected=selected,
            dest_dir=APPIMAGES_DIR,
        )
        if isinstance(result, PackageError):
            _exit_with_error(result)

        appimage_path, verification, warnings = result

        logger.info("Downloaded: %s", appimage_path)
        logger.info("Verification: %s", verification.status.value)

        for warning in warnings:
            _print_package_warning(warning)


def install(url: str) -> None:
    """Install an AppImage from a GitHub repository URL."""
    init_config()
    asyncio.run(_install_async(url))
