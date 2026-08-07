"""Download and verify AppImage assets."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import aiohttp

from .constants import CHUNK_SIZE, DOWNLOAD_SEMAPHORE, HTTP_404
from .models import (
    Asset,
    ChecksumResult,
    DownloadedAsset,
    ErrorCode,
    ErrorKind,
    PackageError,
    PackageWarning,
    SelectedAssets,
    Stage,
    WarningCode,
)
from .verify import verify_downloaded_appimage

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


async def _download_asset(
    session: aiohttp.ClientSession,
    asset: Asset,
    dest_dir: Path,
    package: str,
) -> DownloadedAsset | PackageError:
    """Stream one asset to disk under DOWNLOAD_SEMAPHORE.

    This function downloads an asset from the given URL and saves it
    to the specified destination directory. It uses a semaphore to limit
    concurrent downloads.

    Args:
        session: The aiohttp client session to use for the download.
        asset: The Asset object representing the asset to download.
        dest_dir: The destination directory to save the downloaded asset.
        package: The name of the package being downloaded.

    Returns:
        DownloadedAsset: The result of the download, including the path to
                         the downloaded file.
        PackageError: If the download fails due to network or HTTP errors.
    """
    dest_path = dest_dir / asset.name
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=60)

    logger.debug("Downloading asset: %s to %s", asset.download_url, dest_path)

    # Use a semaphore to limit concurrent downloads
    async with DOWNLOAD_SEMAPHORE:
        try:
            # same patterns as api.py: session.get() doesn't fetch anything by
            # itself. entering this sends the GET request and pauses until
            # response headers arrive. Other tasks(other downloads, installs)
            # run while we wait here.
            async with session.get(
                asset.download_url, timeout=timeout
            ) as response:
                if response.status == HTTP_404:
                    return PackageError(
                        package=package,
                        kind=ErrorKind.ASSET,
                        code=ErrorCode.APPIMAGE_ASSET_NOT_FOUND,
                        stage=Stage.DOWNLOAD.value,
                        retryable=True,
                    )
                response.raise_for_status()

                logger.debug(
                    "Response status: %s, content length: %s",
                    response.status,
                    response.headers.get("Content-Length"),
                )
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")
                logger.debug("Creating temporary file: %s", tmp_path)
                with tmp_path.open("wb") as fh:
                    logger.debug(
                        "Downloading asset to temporary file: %s", tmp_path
                    )
                    # this is an "async generator" loop. Instead of
                    # await response.read() (which waits for the whole file
                    # to be downloaded), this hands you 256kB chunks as they
                    # arrives over the network, pausing this task between chunks.
                    # That's why an AppImage never has to sit fully in memory,
                    # each chunk is written to disk and then thrown away.
                    async for chunk in response.content.iter_chunked(
                        CHUNK_SIZE
                    ):
                        # writing to a local file is fast so using synchronous
                        _ = fh.write(chunk)
                    # rename the temporary file to the final destination path
                    _ = tmp_path.replace(dest_path)
                    logger.debug(
                        "Download complete, moved to final path: %s", dest_path
                    )
        except aiohttp.ClientConnectorError:
            return PackageError(
                package=package,
                kind=ErrorKind.NETWORK,
                code=ErrorCode.NETWORK_DNS_FAILURE,
                stage=Stage.DOWNLOAD.value,
                retryable=True,
            )
        except (TimeoutError, aiohttp.ClientError):
            return PackageError(
                package=package,
                kind=ErrorKind.NETWORK,
                code=ErrorCode.NETWORK_TIMEOUT,
                stage=Stage.DOWNLOAD.value,
                retryable=True,
            )
    return DownloadedAsset(asset=asset, path=dest_path)


# TODO: we might change checksum install seperate function?
async def download_and_verify(
    session: aiohttp.ClientSession,
    package: str,
    selected: SelectedAssets,
    dest_dir: Path,
) -> tuple[Path, ChecksumResult, list[PackageWarning]] | PackageError:
    """Download AppImage (+checksum_file if detected) concurrently then verify.

    Args:
        session: The aiohttp client session to use for the download.
        package: The name of the package being downloaded.
        selected: The SelectedAssets object containing the assets to download.
        dest_dir: The destination directory to save the downloaded assets.

    Returns:
        tuple: The path to the downloaded AppImage, the result of the checksum
               verification, and any warnings encountered during verification.
        PackageError: If the download or verification fails due to network,
                      HTTP, or checksum errors.
    """
    logger.debug(
        "Starting download and verification for package: %s, selected assets: %s",
        package,
        selected,
    )
    # ensure_future() is schedules the AppImage download to start now,
    # without blocking to wait for it. It goes into a plain list of tasks,
    # same idea as install.py's, just smaller scale.
    tasks: list[asyncio.Task[DownloadedAsset | PackageError]] = [
        asyncio.ensure_future(
            _download_asset(session, selected.appimage, dest_dir, package)
        )
    ]
    if selected.checksum_file is not None:
        # ensure_future() is schedules the checksum download to start now if
        # it exists. Both were ensure_future before any await/gather, so they
        # start running concurrently. The appimage and it's checksum file
        # download at the same time instead of one after the other.
        tasks.append(
            asyncio.ensure_future(
                _download_asset(
                    session, selected.checksum_file, dest_dir, package
                )
            )
        )

    # await + gather waits for both downloads (or the single if no checksum)
    # to finish, and returns a list of results in the same order as the tasks
    # were added.
    results = await asyncio.gather(*tasks)

    appimage_result = results[0]
    if isinstance(appimage_result, PackageError):
        return appimage_result
    appimage_path = appimage_result.path

    checksum_path: Path | None = None
    warnings: list[PackageWarning] = []
    if len(results) > 1:
        checksum_result = results[1]
        if isinstance(checksum_result, PackageError):
            # checksum asset existed in the release but failed to fetch
            # degrade to "no usable checksum" rather than failing the install
            warnings.append(
                PackageWarning(
                    package=package,
                    code=WarningCode.NO_CHECKSUM_UNSUPPORTED,
                    stage=Stage.VERIFY.value,
                )
            )
        else:
            checksum_path = checksum_result.path

    # verify the downloaded AppImage using the checksum file if it exists
    verification, verify_warnings = verify_downloaded_appimage(
        appimage_path, selected.appimage, checksum_path
    )
    warnings.extend(verify_warnings)

    return appimage_path, verification, warnings
