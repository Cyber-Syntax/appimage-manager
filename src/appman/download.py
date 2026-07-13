"""Download and verify AppImage assets."""

from __future__ import annotations

import asyncio
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


# find the browser_download_url for appimage
# find checksum_file browser_download_url if exist else skip
# request download for that appimage
async def _download_asset(
    session: aiohttp.ClientSession,
    asset: Asset,
    dest_dir: Path,
    package: str,
) -> DownloadedAsset | PackageError:
    """Stream one asset to disk under DOWNLOAD_SEMAPHORE.

    Never raises across the module boundry, network and HTTP failures
    come back as PackageError.
    """
    dest_path = dest_dir / asset.name
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=60)

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

                dest_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")
                with tmp_path.open("wb") as fh:
                    async for chunk in response.content.iter_chunked(
                        CHUNK_SIZE
                    ):
                        fh.write(chunk)
                    tmp_path.replace(dest_path)
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


# FIXME: type errors
async def download_and_verify(
    session: aiohttp.ClientSession,
    package: str,
    selected: SelectedAssets,
    dest_dir: Path,
) -> tuple[Path, ChecksumResult, list[PackageWarning]] | PackageError:
    """Download the AppImage ( + checksum_file if detected) concurrently then verify."""
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
