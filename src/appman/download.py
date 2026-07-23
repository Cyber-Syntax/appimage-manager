"""Download and verify AppImage assets."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import aiohttp

from .constants import CHUNK_SIZE, DOWNLOAD_SEMAPHORE
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
    async with DOWNLOAD_SEMAPHORE:
        try:
            async with session.get(
                asset.download_url, timeout=timeout
            ) as response:
                if response.status == 404:
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
                    async for chunk in response.content.iter_chunked(
                        CHUNK_SIZE
                    ):
                        fh.write(chunk)
                    tmp_path.replace(dest_path)
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
# FIXME: type errors
async def download_and_verify(
    session: aiohttp.ClientSession,
    package: str,
    selected: SelectedAssets,
    dest_dir: Path,
) -> tuple[Path, ChecksumResult, list[PackageWarning]] | PackageError:
    """Download the AppImage (+checksum_file if detected) concurrently then verify.

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
    tasks: list[asyncio.Task] = [
        asyncio.ensure_future(
            _download_asset(session, selected.appimage, dest_dir, package)
        )
    ]
    if selected.checksum_file is not None:
        tasks.append(
            asyncio.ensure_future(
                _download_asset(
                    session, selected.checksum_file, dest_dir, package
                )
            )
        )

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

    verification, verify_warnings = verify_downloaded_appimage(
        appimage_path, selected.appimage, checksum_path
    )
    warnings.extend(verify_warnings)

    return appimage_path, verification, warnings
