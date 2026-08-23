"""Install orchestration for appman."""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from .api import fetch_latest_release, parse_github_url, select_appimage_asset
from .constants import APPIMAGES_DIR
from .download import download_and_verify
from .models import (
    ERROR_MESSAGES,
    INFO_MESSAGES,
    WARNING_MESSAGES,
    ErrorCode,
    ErrorKind,
    InfoCode,
    PackageError,
    PackageWarning,
    Stage,
    WarningCode,
)

logger = logging.getLogger(__name__)

# fallbacks for codes that somehow aren't in the message dicts
_UNKOWN_ERROR_MESSAGE = ERROR_MESSAGES[ErrorCode.UNKNOWN_ERROR]
_UNKOWN_WARNING_MESSAGE = WARNING_MESSAGES[WarningCode.UNKNOWN_WARNING]


def _print_package_error(error: PackageError) -> None:
    """Print a structured install failure message.

    Args:
        error: The package error to print.

    Returns:
        None
    """
    message = ERROR_MESSAGES.get(error.code, _UNKOWN_ERROR_MESSAGE)
    logger.error(
        "%s: %s/%s at %s (retryable=%s) - %s",
        error.package,
        error.kind.value,
        error.code.value,
        error.stage,
        error.retryable,
        message,
    )


def _print_package_warning(warning: PackageWarning) -> None:
    """Print a structured install warning message.

    Args:
        warning: The package warning to print.

    Returns:
        None
    """
    message = WARNING_MESSAGES.get(warning.code, _UNKOWN_WARNING_MESSAGE)
    logger.warning(
        "%s: %s at %s - %s",
        warning.package,
        warning.code.value,
        warning.stage,
        message,
    )


def _dedupe_urls(urls: list[str]) -> tuple[list[str], list[PackageWarning]]:
    """Drop duplicate install targets, keeping first occurrence.

    Dedup key is the parsed (owner, repo) pair, case-folded, so
    'https://github.com/pbek/QOwnNotes' and the same URL with a
    trailing '.git' collapse to one target instead of racing two
    concurrent downloads into the same dest_path (see download.py).
    URLs that fail to parse are kept as-is (deduped by raw string only)
    so they still surface their own INVALID_URL PackageError downstream.

    Args:
        urls: The raw list of install targets from argparse.

    Returns:
        A tuple of (deduplicated urls, warnings for each duplicate dropped).
    """
    # python built-in set() store unique values only
    seen: set[tuple[str, str] | str] = set()
    # stores the unique URLs we want to keep
    deduped: list[str] = []
    # stores warnings about duplicates we skipped
    warnings: list[PackageWarning] = []

    for url in urls:
        parsed = parse_github_url(url)
        key: tuple[str, str] | str  # (owner, repo) or str

        # check whether parsing failed
        if isinstance(parsed, PackageError):
            key = url
        else:
            owner, repo = parsed
            key = (owner.casefold(), repo.casefold())

        # check for any duplicated in seen set and skip if duplicated
        if key in seen:
            # label is repo name(key[1]) to show in warning if tuple, else url
            label = key[1] if isinstance(key, tuple) else url
            logger.debug("Dropping duplicate install target: %s", url)
            warnings.append(
                PackageWarning(
                    package=label,
                    code=WarningCode.DUPLICATE_TARGET_SKIPPED,
                    stage=Stage.QUERY.value,
                )
            )
            # stop processing this duplicated URL right now,
            # go to next URL in the for loop
            continue

        # add unique key to seen set
        seen.add(key)
        # add unique url to deduped
        deduped.append(url)

    return deduped, warnings


# NOTE: "async def" is used here because it's body contains "await" calls
# that talk to the network (fetch_latest_release, download_and_verify).
# Being async doesn't make this function run concurrently by itself
# it just means this function is allowed to "pause and resume" at await points,
# so other tasks can run while this one is waiting for network I/O to complete.
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
    # fallback label until/unless parse_github_url resolves a repo name
    package = url
    try:
        parse_result = parse_github_url(url)
        if isinstance(parse_result, PackageError):
            # no owner/repo yet, use the raw url as the reported "package"
            return parse_result.package, parse_result

        owner, repo = parse_result
        package = repo
        logger.debug("Parsed GitHub URL: owner=%s, repo=%s", owner, repo)

        # NOTE: "await" is used here because GitHub API over the network is involved,
        # "await" means "pause this function until the response comes back.".
        # while paused, the event loop is free to run other _install_one() tasks
        # for other URLs in the same batch, so they can all run concurrently.
        release = await fetch_latest_release(session, owner, repo, package)
        if isinstance(release, PackageError):
            return package, release

        # select_appimage_asset now returns SelectedAssets directly
        # it resolves both the appimage and its matching checksum/digest file
        # in one pass, so no manual SelectedAssets() wrap here anymore
        selected = select_appimage_asset(release.assets, package)
        if isinstance(selected, PackageError):
            return package, selected

        logger.debug(
            "Selected AppImage asset: name=%s",
            selected.appimage.name,
        )

        # NOTE: downloads + verification for this one package. Internally this
        # function does it's own concurrency (see download.py),
        # but here mean "wait for this whole step to finish"
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

    except Exception:
        # last-resort boundary guard — an unexpected exception (e.g. a
        # malformed API payload raising KeyError during parsing) must not
        # propagate through gather() and cancel sibling in-flight installs.
        # `package` is the best label available at this point: the repo
        # name if parsing already succeeded, otherwise the raw URL.
        logger.exception("Unexpected error installing %s", package)
        return package, PackageError(
            package=package,
            kind=ErrorKind.INTERNAL,
            code=ErrorCode.UNKNOWN_ERROR,
            stage=Stage.QUERY.value,
            retryable=False,
        )
    else:
        return package, release.tag_name  # success


# this func whole job is the launch many _install_one() tasks concurrently
# and wait for them all to finish.
# (e.g 2 urls install -> 2 _install_one() tasks running concurrently)
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
    # opens one shared aiohttp.ClientSession for the whole batch of URLs,
    # so we don't have to open/close a new session for each URL.
    # "with" guarantees the session is closed when this function exits,
    # even if an exception occurs.
    async with aiohttp.ClientSession() as session:
        # ensure_future(): this schedules each _install_one() coroutine
        # to start running right away without waiting for it to finish.
        # so this inside a loop is how you "fire off" many tasks at once
        # instead of running them one after another.
        tasks = [
            asyncio.ensure_future(_install_one(session, url)) for url in urls
        ]
        # asyncio.gather() is used to wait for all the tasks to finish together,
        # not one at a time. While tasks 1 is waiting on the network, task 2
        # can be making progress, and so on. gather returns the results
        # in the same order the tasks were created, once everything is done.
        # also gather is safe for errors on _install_one because that func
        # never raises.
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

    deduped_urls, dedupe_warnings = _dedupe_urls(urls)
    for warning in dedupe_warnings:
        _print_package_warning(warning)

    # asyncio.run() is the bridge between sync (argparse, cli.py, etc.) and the
    # async (_install_all_async and everything it calls).
    # this starts an event loop, runs the async function until it completely
    # done, then shuts the loop down and hands back a plain value,
    # so the rest of this func can stay totally normal, synchronous.
    results = asyncio.run(_install_all_async(deduped_urls))

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

    # this would only reached after asyncio.run() has already returned
    if failed:
        raise SystemExit(1)  # partial or total failure
    # all succeeded -> return None, exit 0
