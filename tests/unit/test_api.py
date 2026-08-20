"""Unit tests for appman.api -- GitHub REST client."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import aiohttp
import pytest

from appman.api import (
    _parse_release_asset,
    _parse_release_data,
    cache_release_data,
    classify_asset_type,
    fetch_latest_release,
    is_amd64,
    is_incompatible_platform,
    is_unstable,
    parse_asset,
    parse_github_url,
    select_appimage_asset,
)
from appman.models import (
    AssetType,
    ErrorCode,
    ErrorKind,
    PackageError,
    ReleaseAsset,
)


# Helpers
def make_release_asset(
    name: str,
    *,
    download_url: str = "https://example.com/assset",
    size: int = 1024,
    content_type: str = "application/octet-stream",
    digest: str | None = None,
) -> ReleaseAsset:
    """Build a ReleaseAsset with sensible defaults for tests."""
    return ReleaseAsset(
        name=name,
        download_url=download_url,
        size=size,
        content_type=content_type,
        digest=digest,
    )


class _FakeResponse:
    """Minimal async-context-manager double for aiohttp's response object."""

    def __init__(
        self,
        status: int = 200,
        json_body: dict[str, Any] | None = None,
        raise_on_status: bool = False,
    ) -> None:
        self.status = status
        self._json_body = json_body or {}
        self._raise_on_status = raise_on_status
        self.headers: dict[str, str] = {}

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self._raise_on_status:
            raise aiohttp.ClientResponseError(
                request_info=MagicMock(), history=(), status=self.status
            )

    async def json(self) -> dict[str, Any]:
        return self._json_body


class _FakeSession:
    """Fakes session.get(...) returning a pre-built _FakeResponse."""

    def __init__(self, response: _FakeResponse | Exception) -> None:
        self._response = response

    def get(self, *_args: object, **_kwargs: object) -> _FakeResponse:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


@pytest.fixture
def sample_release_payload() -> dict[str, Any]:
    """A minimal, valid GitHub 'release/latest' JSON payload."""
    return {
        "tag_name": "v1.2.3",
        "name": "MyApp 1.2.3",
        "prerelease": False,
        "published_at": "2026-01-01T00:00:00Z",
        "assets": [
            {
                "name": "MyApp-x86_64.AppImage",
                "browser_download_url": "https://gh.example/MyApp.AppImage",
                "size": 12345,
                "content_type": "application/octet-stream",
                "digest": "sha256:abc123",
            }
        ],
    }


# parse_github_url
class TestParseGithubUrl:
    @pytest.mark.parametrize(
        "url, expected_owner, expected_repo",
        [
            ("https://github.com/pbek/QOwnNotes", "pbek", "QOwnNotes"),
            ("https://github.com/pbek/QOwnNotes.git", "pbek", "QOwnNotes"),
            ("git@github.com:pbek/QOwnNotes.git", "pbek", "QOwnNotes"),
            ("http://github.com/foo/bar", "foo", "bar"),
        ],
    )
    def test_parses_valid_urls(
        self, url: str, expected_owner: str, expected_repo: str
    ) -> None:
        """Valid GitHub URL's of every supported shape resolve to (owner, repo)."""
        result = parse_github_url(url)
        assert result == (expected_owner, expected_repo)

    @pytest.mark.parametrize(
        "bad_url",
        [
            "https://google.com/foo/bar",  # unsupported host
            "not a url at all",
            "",
        ],
    )
    def test_invalid_url_returns_package_error(self, bad_url: str) -> None:
        """unsupported/malformed URLs return a structured error, never raise."""
        result = parse_github_url(bad_url)
        assert isinstance(result, PackageError)
        assert result.kind == ErrorKind.VALIDATION
        assert result.code == ErrorCode.INVALID_URL
        assert result.package == bad_url  # raw url preserved for reporting


# fetch_latest_release
class TestFetchLatestRelease:
    @pytest.mark.asyncio
    async def test_success_parses_release_and_caches_it(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sample_release_payload: dict[str, Any],
    ) -> None:
        """200 response is parsed into a GitHubRelease and handed to the cache."""
        cache_spy = MagicMock()
        monkeypatch.setattr("appman.api.cache_release_data", cache_spy)

        session = _FakeSession(
            _FakeResponse(status=200, json_body=sample_release_payload)
        )

        result = await fetch_latest_release(
            session, "pbek", "QOwnNotes", "qownnotes"
        )

        assert not isinstance(result, PackageError)
        assert result.tag_name == "v1.2.3"
        assert result.prerelease is False
        assert len(result.assets) == 1
        assert result.assets[0].name == "MyApp-x86_64.AppImage"

        # contract: successful fetch always caches the raw payload
        cache_spy.assert_called_once_with(
            "pbek", "QOwnNotes", sample_release_payload
        )

    @pytest.mark.asyncio
    async def test_404_returns_asset_not_found_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 404 means no release/asset -- returned as retryable, never raised."""
        monkeypatch.setattr("appman.api.cache_release_data", MagicMock())
        session = _FakeSession(_FakeResponse(status=404))

        result = await fetch_latest_release(session, "owner", "repo", "pkg")

        assert isinstance(result, PackageError)
        assert result.code == ErrorCode.APPIMAGE_ASSET_NOT_FOUND
        assert result.retryable is True

    @pytest.mark.asyncio
    async def test_dns_failure_returns_network_dns_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Connection-level DNS failure maps to NETWORK_DNS_FAILURE, not a crash."""
        monkeypatch.setattr("appman.api.cache_release_data", MagicMock())
        session = _FakeSession(
            aiohttp.ClientConnectorError(MagicMock(), OSError("no dns"))
        )

        result = await fetch_latest_release(session, "owner", "repo", "pkg")

        assert isinstance(result, PackageError)
        assert result.code == ErrorCode.NETWORK_DNS_FAILURE
        assert result.retryable is True

    @pytest.mark.asyncio
    async def test_timeout_returns_network_timeout_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """slow/unresponsive upstream maps to NETWORK_TIMEOUT."""
        monkeypatch.setattr("appman.api.cache_release_data", MagicMock())
        session = _FakeSession(TimeoutError())

        result = await fetch_latest_release(session, "owner", "repo", "pkg")

        assert isinstance(result, PackageError)
        assert result.code == ErrorCode.NETWORK_TIMEOUT

    @pytest.mark.asyncio
    async def test_non_404_http_error_raises_for_status_is_handled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A non-404 HTTP error (e.g 500) surfaces via ClientError -> NETWORK_TIMEOUT path."""
        monkeypatch.setattr("appman.api.cache_release_data", MagicMock())
        session = _FakeSession(_FakeResponse(status=500, raise_on_status=True))

        result = await fetch_latest_release(session, "owner", "repo", "pkg")

        assert isinstance(result, PackageError)
        assert result.kind == ErrorKind.NETWORK


# _parse_release_data / _parse_release_asset
class TestParseReleaseData:
    def test_falls_back_to_tag_name_when_name_missing(self) -> None:
        """Github's name field is optional; release_name should fall back to tag_name."""
        raw = {
            "tag_name": "v2.0.0",
            "prerelease": False,
            "published_at": "2026-01-01T00:00:00Z",
            "assets": [],
        }
        release = _parse_release_data(raw)
        assert release.release_name == "v2.0.0"

    def test_strips_sha256_prefix_from_digest(self) -> None:
        """Digest is normalized to hex-only; the sha256 prefix must be stripped."""
        raw_asset = {
            "name": "app.AppImage",
            "browser_download_url": "https://x/app.AppImage",
            "size": 10,
            "digest": "sha256:deadbeef",
        }
        asset = _parse_release_asset(raw_asset)
        assert asset.digest == "deadbeef"

    def test_missing_digest_stays_none(self) -> None:
        """No digest key present -> digest is None, not an empty string or KeyError."""
        raw_asset = {
            "name": "app.AppImage",
            "browser_download_url": "https://x/app.AppImage",
            "size": 10,
        }
        asset = _parse_release_asset(raw_asset)
        assert asset.digest is None


# TODO: add more example, use your filter .md file
# select_appimage_asset
class TestSelectAppimageAsset:
    def test_no_appimage_assets_returns_error(self) -> None:
        """A release with no .appimage assets at all is a clean, typed failure."""
        assets = [make_release_asset("app.dmg"), make_release_asset("app.exe")]
        result = select_appimage_asset(assets, "pkg")
        assert isinstance(result, PackageError)
        assert result.code == ErrorCode.APPIMAGE_ASSET_NOT_FOUND

    def test_filters_out_incompatible_platform_assets(self) -> None:
        """windows/macos appimage-named not supported yet."""
        assets = [
            make_release_asset("app-mac.AppImage"),
            make_release_asset("app-x86_64.AppImage"),
        ]
        result = select_appimage_asset(assets, "pkg")
        assert not isinstance(result, PackageError)
        assert result.appimage.name == "app-x86_64.AppImage"

    def test_prefers_stable_over_beta_when_both_exist(self) -> None:
        """A stable release wins over a beta build when both are present."""
        assets = [
            make_release_asset("app-beta-x86_64.AppImage"),
            make_release_asset("app-x86_64.AppImage"),
        ]
        result = select_appimage_asset(assets, "pkg")
        assert result.appimage.name == "app-x86_64.AppImage"

    def test_keeps_beta_when_all_candidates_are_unstable(self) -> None:
        """Freetube style apps that are always beta must still be installable."""
        assets = [make_release_asset("app-beta-x86_64.AppImage")]
        result = select_appimage_asset(assets, "pkg")
        assert not isinstance(result, PackageError)
        assert result.appimage.name == "app-beta-x86_64.AppImage"

    def test_prefers_amd64_asset_when_multiple_arch_present(self) -> None:
        """x86_64/amd64 is preferred over other arch when both are stable."""
        assets = [
            make_release_asset("app-arm64.AppImage"),  # incompatible
            make_release_asset("app-x86_64.AppImage"),
        ]
        result = select_appimage_asset(assets, "pkg")
        assert result.appimage.name == "app-x86_64.AppImage"

    def test_falls_back_to_first_match_when_no_amd64_present(self) -> None:
        """If nothing is explicitly amd64/x86_64, fallback to generic name."""
        assets = [make_release_asset("app.AppImage")]
        result = select_appimage_asset(assets, "pkg")
        assert result.appimage.name == "app.AppImage"

    def test_selects_per_file_checksum_matching_the_appimage_by_prefix(
        self,
    ) -> None:
        """A checksum file named after the appimage is paired with it by prefix match."""
        assets = [
            make_release_asset("QOwnNotes-x86_64.AppImage"),
            make_release_asset("QOwnNotes-x86_64.AppImage.sha256sum"),
        ]
        result = select_appimage_asset(assets, "pkg")
        assert not isinstance(result, PackageError)
        assert result.checksum_file is not None
        assert (
            result.checksum_file.name == "QOwnNotes-x86_64.AppImage.sha256sum"
        )

    def test_falls_back_to_release_wide_checksum_manifest(self) -> None:
        """When no per-file checksum exists, a release-wide manifest (SHA256SUMS) is used."""
        assets = [
            make_release_asset("KeePassXC-2.7.10-x86_64.AppImage"),
            make_release_asset("SHA256SUMS"),
        ]
        result = select_appimage_asset(assets, "pkg")
        assert not isinstance(result, PackageError)
        assert result.checksum_file is not None
        assert result.checksum_file.name == "SHA256SUMS"

    def test_checksum_file_is_none_when_none_present(self) -> None:
        """No checksum/digest asset in the release is a normal outcome, not an error."""
        assets = [make_release_asset("app-x86_64.AppImage")]
        result = select_appimage_asset(assets, "pkg")
        assert not isinstance(result, PackageError)
        assert result.checksum_file is None

    def test_excludes_incompatible_platform_checksum_file(self) -> None:
        """A macos/win checksum file must not be mistake for a linux match."""
        assets = [
            make_release_asset("KeePassXC-2.7.10-x86_64.AppImage"),
            make_release_asset("KeePassXC-2.7.10-x86_64.dmg.DIGEST"),
        ]
        result = select_appimage_asset(assets, "pkg")
        assert not isinstance(result, PackageError)
        assert result.checksum_file is None


# parse_asset / classify_asset_type


class TestParseAsset:
    def test_classifies_and_carries_digest_through(self) -> None:
        raw = make_release_asset("app.AppImage", digest="abc123")
        asset = parse_asset(raw)
        assert asset.asset_type == AssetType.APPIMAGE
        assert asset.digest == "abc123"


class TestClassifyAssetType:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("app.AppImage", AssetType.APPIMAGE),
            ("app.appimage", AssetType.APPIMAGE),
            ("app.sha256", AssetType.CHECKSUM_FILE),
            ("app.DIGEST", AssetType.CHECKSUM_FILE),
            ("SHA256SUMS", AssetType.CHECKSUM_FILE),
            ("SHA256SUMS.txt", AssetType.CHECKSUM_FILE),
            ("latest-linux.yml", AssetType.CHECKSUM_FILE),
            ("app.dmg", AssetType.OTHER_TYPE),
            ("app.exe", AssetType.OTHER_TYPE),
        ],
    )
    def test_classifies_by_extension(
        self, name: str, expected: AssetType
    ) -> None:
        assert classify_asset_type(name) == expected


class TestIsIncompatiblePlatform:
    @pytest.mark.parametrize(
        "name",
        [
            "app-win64.AppImage",
            "app.dmg",
            "app-mac.AppImage",
            "app-arm64.AppImage",
            "app-src.tar.gz",
            "KeePassXC-2.7.10-Win64.zip.DIGEST",  # embedded, not true suffix
            "KeePassXC-2.7.10-x86_64.dmg.DIGEST",  # embedded, not true suffix
        ],
    )
    def test_flags_incompatible_names(self, name: str) -> None:
        assert is_incompatible_platform(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "app-x86_64.AppImage",
            "app-linux-amd64.AppImage",
            "QOwnNotes-x86_64.AppImage.sha256sum",
        ],
    )
    def test_allows_compatible_names(self, name: str) -> None:
        assert is_incompatible_platform(name) is False


class TestIsUnstable:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("app-beta.AppImage", True),
            ("app-rc1.AppImage", True),
            ("app-nightly.AppImage", True),
            ("app-1.2.3.AppImage", False),
        ],
    )
    def test_detects_unstable_keywords(
        self, name: str, expected: bool
    ) -> None:
        assert is_unstable(name) is expected


class TestIsAmd64:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("app-x86_64.AppImage", True),
            ("app-amd64.AppImage", True),
            ("app-arm64.AppImage", False),
            ("app-i386.AppImage", False),
        ],
    )
    def test_detects_amd64(self, name: str, expected: bool) -> None:
        assert is_amd64(name) is expected


# cache_release_data
class TestCacheReleaseData:
    def test_writes_json_payload_to_expected_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """Cache file is written under CACHE_DIR using the "owner_repo_latest.json" name."""
        monkeypatch.setattr("appman.api.CACHE_DIR", tmp_path)

        payload = {"tag_name": "v1.0.0", "assets": []}
        cache_release_data("owner", "repo", payload)

        expected_file = tmp_path / "owner_repo_latest.json"
        assert expected_file.exists()
        assert json.loads(expected_file.read_bytes()) == payload
