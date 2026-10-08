from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from appman.download import _download_asset, download_and_verify
from appman.models import (
    ChecksumResult,
    DownloadedAsset,
    ErrorCode,
    ErrorKind,
    PackageError,
    PackageWarning,
    Stage,
    VerificationStatus,
    WarningCode,
)


class FakeContent:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    async def iter_chunked(self, _chunk_size: int):
        for chunk in self.chunks:
            yield chunk


class FakeResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        chunks: list[bytes] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.status = status
        self.headers = {"Content-Length": "3"}
        self.content = FakeContent(chunks=chunks or [])
        self._error = error

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self._error is not None:
            raise self._error


class FailingContent:
    async def iter_chunked(self, _chunk_size: int):
        yield b"partial"
        raise aiohttp.ClientError("Simulated network error during download")


@pytest.mark.asyncio
async def test_download_asset_removes_partial_file_on_stream_error(
    tmp_path: Path,
) -> None:
    asset = SimpleNamespace(
        name="app.AppImage", download_url="http://example.com/app/desktop"
    )

    response = FakeResponse()
    response.content = FailingContent()

    session = MagicMock()
    session.get.return_value = response

    result = await _download_asset(session, asset, tmp_path, "test-package")

    assert isinstance(result, PackageError)
    assert result.code == ErrorCode.NETWORK_TIMEOUT
    assert result.kind == ErrorKind.NETWORK
    assert result.stage == Stage.DOWNLOAD.value
    assert result.retryable is True

    # Ensure that the partial file is removed after the download error
    assert not (tmp_path / "app.AppImage.part").exists()


@pytest.mark.asyncio
async def test_download_asset_returns_permission_error_for_dest_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset = SimpleNamespace(
        name="app.AppImage", download_url="http://example.com/app/desktop"
    )

    def fail_open(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("permission error")

    monkeypatch.setattr(Path, "open", fail_open)

    session = MagicMock()
    session.get.return_value = FakeResponse()

    result = await _download_asset(session, asset, tmp_path, "test-package")

    assert isinstance(result, PackageError)
    assert result.kind == ErrorKind.FILESYSTEM
    assert result.code == ErrorCode.PERMISSION_DENIED
    assert result.stage == Stage.DOWNLOAD.value


@pytest.mark.asyncio
async def test_download_asset_ignores_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset = SimpleNamespace(
        name="app.AppImage", download_url="http://example.com/app/desktop"
    )

    response = FakeResponse()
    response.content = FailingContent()

    def fail_unlink(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated unlink error")

    monkeypatch.setattr(Path, "unlink", fail_unlink)

    session = MagicMock()
    session.get.return_value = response

    result = await _download_asset(session, asset, tmp_path, "test-package")

    assert isinstance(result, PackageError)
    assert result.kind == ErrorKind.NETWORK
    assert result.code == ErrorCode.NETWORK_TIMEOUT
    assert result.stage == Stage.DOWNLOAD.value


@pytest.mark.asyncio
async def test_download_asset_returns_filesystem_error_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset = SimpleNamespace(
        name="app.AppImage", download_url="http://example.com/app/desktop"
    )
    # create magic mock for the file handle returned by Path.open
    file_handle = MagicMock()

    # Simulate the context manager behavior of the file handle
    file_handle.__enter__.return_value = file_handle

    # Simulate the write method raising an OSError
    file_handle.write.side_effect = OSError("simulated write error")

    # Patch Path.open to return the mocked file handle
    monkeypatch.setattr(Path, "open", MagicMock(return_value=file_handle))

    # session.get should return a FakeResponse with some chunks to write
    session = MagicMock()
    session.get.return_value = FakeResponse()

    result = await _download_asset(session, asset, tmp_path, "test-package")

    assert isinstance(result, PackageError)
    assert result.kind == ErrorKind.FILESYSTEM
    assert result.code == ErrorCode.FILESYSTEM_WRITE_ERROR
    assert result.stage == Stage.DOWNLOAD.value
    assert result.retryable is False


@pytest.mark.asyncio
async def test_download_asset_writes_file(tmp_path: Path) -> None:
    asset = SimpleNamespace(
        name="app.AppImage", download_url="http://example.com/app/desktop"
    )

    response = FakeResponse(chunks=[b"app", b"image"])

    session = MagicMock()
    session.get.return_value = response

    result = await _download_asset(session, asset, tmp_path, "test-package")

    assert isinstance(result, DownloadedAsset)
    assert result.path == tmp_path / "app.AppImage"
    assert result.path.read_bytes() == b"appimage"
    assert not result.path.with_suffix(result.path.suffix + ".part").exists()


@pytest.mark.asyncio
async def test_download_asset_returns_error_for_404(tmp_path: Path) -> None:
    asset = SimpleNamespace(
        name="app.AppImage", download_url="http://example.com/app/desktop"
    )

    response = FakeResponse(status=404)

    session = MagicMock()
    session.get.return_value = response

    result = await _download_asset(session, asset, tmp_path, "test-package")

    assert isinstance(result, PackageError)
    assert result.code == ErrorCode.APPIMAGE_ASSET_NOT_FOUND
    assert result.kind == ErrorKind.ASSET
    assert result.retryable is True


@pytest.mark.asyncio
async def test_download_asset_returns_network_error_on_timeout(
    tmp_path: Path,
) -> None:
    asset = SimpleNamespace(
        name="app.AppImage", download_url="http://example.com/app/desktop"
    )

    session = MagicMock()
    session.get.side_effect = TimeoutError()

    result = await _download_asset(session, asset, tmp_path, "test-package")

    assert isinstance(result, PackageError)
    assert result.code == ErrorCode.NETWORK_TIMEOUT
    assert result.kind == ErrorKind.NETWORK
    assert result.stage == Stage.DOWNLOAD.value
    assert result.retryable is True


@pytest.mark.asyncio
async def test_download_asset_returns_network_error_on_client_error(
    tmp_path: Path,
) -> None:
    asset = SimpleNamespace(
        name="app.AppImage", download_url="http://example.com/app/desktop"
    )

    session = MagicMock()
    session.get.return_value = FakeResponse(error=aiohttp.ClientError())

    result = await _download_asset(session, asset, tmp_path, "test-package")

    assert isinstance(result, PackageError)
    assert result.code == ErrorCode.NETWORK_TIMEOUT
    assert result.kind == ErrorKind.NETWORK
    assert result.stage == Stage.DOWNLOAD.value
    assert result.retryable is True


@pytest.mark.asyncio
async def test_download_and_verify_downloads_and_verifies_assets(
    tmp_path: Path,
) -> None:
    appimage = SimpleNamespace(
        name="app.AppImage",
        download_url="http://example.com/app/desktop",
    )
    checksum = SimpleNamespace(
        name="app.AppImage.sha256",
        download_url="http://example.com/app/desktop.sha256",
    )
    selected = SimpleNamespace(appimage=appimage, checksum_file=checksum)

    appimage_path = tmp_path / appimage.name
    checksum_path = tmp_path / checksum.name
    verification = MagicMock(spec=ChecksumResult)

    results = [
        DownloadedAsset(asset=appimage, path=appimage_path),
        DownloadedAsset(asset=checksum, path=checksum_path),
    ]

    with (
        patch(
            "appman.download._download_asset",
            new=AsyncMock(side_effect=results),
        ),
        patch(
            "appman.download.verify_downloaded_appimage",
            return_value=(verification, []),
        ) as verify,
    ):
        result = await download_and_verify(
            MagicMock(), "test-package", selected, tmp_path
        )

    assert result == (appimage_path, verification, [])
    verify.assert_called_once_with(appimage_path, appimage, checksum_path)


@pytest.mark.asyncio
async def test_download_and_verify_warns_when_checksum_download_fails(
    tmp_path: Path,
) -> None:
    appimage = SimpleNamespace(
        name="app.AppImage",
        download_url="http://example.com/app/desktop",
    )
    checksum = SimpleNamespace(
        name="app.AppImage.sha256",
        download_url="http://example.com/app/desktop.sha256",
    )
    selected = SimpleNamespace(appimage=appimage, checksum_file=checksum)

    appimage_path = tmp_path / appimage.name
    verification = MagicMock(spec=ChecksumResult)

    checksum_error = PackageError(
        package="test-package",
        kind=ErrorKind.NETWORK,
        code=ErrorCode.NETWORK_TIMEOUT,
        stage=Stage.DOWNLOAD.value,
        retryable=True,
    )

    with (
        patch(
            "appman.download._download_asset",
            new=AsyncMock(
                side_effect=[
                    DownloadedAsset(asset=appimage, path=appimage_path),
                    checksum_error,
                ]
            ),
        ),
        patch(
            "appman.download.verify_downloaded_appimage",
            return_value=(verification, []),
        ) as verify,
    ):
        result = await download_and_verify(
            MagicMock(), "test-package", selected, tmp_path
        )

    assert result[0] == appimage_path
    assert result[1] == verification
    assert len(result[2]) == 1
    assert isinstance(result[2][0], PackageWarning)
    assert result[2][0].code == WarningCode.CHECKSUM_DOWNLOAD_FAILED
    verify.assert_called_once_with(appimage_path, appimage, None)


@pytest.mark.asyncio
async def test_download_and_verify_warns_when_checksum_file_is_unavailable(
    tmp_path: Path,
) -> None:
    appimage = SimpleNamespace(
        name="app.AppImage",
        download_url="http://example.com/app/desktop",
        digests=None,
    )
    appimage_path = tmp_path / appimage.name
    verification = ChecksumResult(status=VerificationStatus.MISSING)

    with (
        patch(
            "appman.download._download_asset",
            new=AsyncMock(
                return_value=DownloadedAsset(
                    asset=appimage, path=appimage_path
                )
            ),
        ),
        patch(
            "appman.download.verify_downloaded_appimage",
            return_value=(verification, []),
        ) as verify,
    ):
        result = await download_and_verify(
            MagicMock(),
            "test-package",
            SimpleNamespace(appimage=appimage, checksum_file=None),
            tmp_path,
        )

        assert not isinstance(result, PackageError)
        assert result[1] is verification
        assert [warning.code for warning in result[2]] == [
            WarningCode.NO_CHECKSUM_UNSUPPORTED
        ]


@pytest.mark.asyncio
async def test_download_and_verify_returns_appimage_download_error(
    tmp_path: Path,
) -> None:
    appimage = SimpleNamespace(
        name="app.AppImage",
        download_url="http://example.com/app/desktop",
    )
    selected = SimpleNamespace(appimage=appimage, checksum_file=None)

    appimage_error = PackageError(
        package="test-package",
        kind=ErrorKind.ASSET,
        code=ErrorCode.APPIMAGE_ASSET_NOT_FOUND,
        stage=Stage.DOWNLOAD.value,
        retryable=True,
    )

    with patch(
        "appman.download._download_asset",
        new=AsyncMock(side_effect=[appimage_error]),
    ):
        result = await download_and_verify(
            MagicMock(), "test-package", selected, tmp_path
        )

    assert isinstance(result, PackageError)
    assert result == appimage_error


@pytest.mark.asyncio
async def test_download_asset_returns_dns_error_on_connector_error(
    tmp_path: Path,
) -> None:
    asset = SimpleNamespace(
        name="app.AppImage", download_url="http://example.com/app/desktop"
    )

    connector_error = aiohttp.ClientConnectorError(
        MagicMock(), OSError("DNS resolution failed")
    )

    session = MagicMock()
    session.get.side_effect = connector_error

    result = await _download_asset(session, asset, tmp_path, "test-package")

    assert isinstance(result, PackageError)
    assert result.code == ErrorCode.NETWORK_DNS_FAILURE
    assert result.kind == ErrorKind.NETWORK
    assert result.stage == Stage.DOWNLOAD.value
    assert result.retryable is True
