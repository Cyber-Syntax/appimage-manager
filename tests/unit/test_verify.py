import hashlib
from pathlib import Path

import pytest

from appman.models import Asset, VerificationStatus, WarningCode
from appman.verify import _parse_checksum_file, verify_downloaded_appimage

APPIMAGE_NAME = "example.AppImage"


@pytest.fixture
def appimage(tmp_path: Path) -> Path:
    appimage = tmp_path / APPIMAGE_NAME
    appimage.write_bytes(b"dummy content")
    return appimage


@pytest.fixture
def appimage_digest() -> str:
    return hashlib.sha256(b"dummy content").hexdigest()


def write_checksum(tmp_path: Path, content: str) -> Path:
    checksum_file = tmp_path / "checksum.txt"
    checksum_file.write_text(content)
    return checksum_file


def make_asset(digest: str | None = None) -> Asset:
    return Asset(
        name=APPIMAGE_NAME,
        download_url="https://example.com/example.AppImage",
        size=1,
        asset_type="AppImage",
        digest=digest,
    )


def test_parse_bare_checksum() -> None:
    checksum = "a" * 64

    assert _parse_checksum_file(checksum, APPIMAGE_NAME) == checksum


def test_parse_checksum_file_accepts_binary_marker_and_path() -> None:
    checksum = "c" * 64
    content = f"{checksum} *./releases/{APPIMAGE_NAME}\n"

    assert _parse_checksum_file(content, APPIMAGE_NAME) == checksum


def test_parse_checksum_file_returns_none_for_invalid_content() -> None:
    assert _parse_checksum_file("invalid content", APPIMAGE_NAME) is None


def test_verify_with_matching_embedded_digest(
    appimage: Path, appimage_digest: str
) -> None:

    result, warnings = verify_downloaded_appimage(
        appimage,
        make_asset(appimage_digest),
        None,
    )

    assert result.status is VerificationStatus.VERIFIED
    assert result.method == "digest"
    assert result.actual_hash == appimage_digest
    assert warnings == []


def test_verify_with_matching_checksum_file(
    appimage: Path, appimage_digest: str, tmp_path: Path
) -> None:
    checksum_file = write_checksum(
        tmp_path, f"{appimage_digest} {APPIMAGE_NAME}\n"
    )

    result, warnings = verify_downloaded_appimage(
        appimage,
        make_asset(),
        checksum_file,
    )

    assert result.status is VerificationStatus.VERIFIED
    assert result.method == "checksum_file"
    assert warnings == []


def test_verify_with_both_matching_methods(
    appimage: Path, appimage_digest: str, tmp_path: Path
) -> None:
    checksum_file = write_checksum(
        tmp_path, f"{appimage_digest} {APPIMAGE_NAME}\n"
    )

    result, warnings = verify_downloaded_appimage(
        appimage,
        make_asset(appimage_digest),
        checksum_file,
    )

    assert result.status is VerificationStatus.VERIFIED
    assert result.method == "digest+checksum_file"
    assert warnings == []


def test_digest_mismatch_fails_even_when_checksum_file_matches(
    appimage: Path, appimage_digest: str, tmp_path: Path
) -> None:
    checksum_file = write_checksum(
        tmp_path, f"{appimage_digest} {APPIMAGE_NAME}\n"
    )

    # Provide a different digest to simulate a mismatch
    wrong_digest = "0" * 64

    result, warnings = verify_downloaded_appimage(
        appimage,
        make_asset(wrong_digest),
        checksum_file,
    )

    assert result.status is VerificationStatus.FAILED
    assert result.method == "digest"
    assert warnings == []


def test_corrupt_checksum_file_is_warning_when_digest_passes(
    appimage: Path, appimage_digest: str, tmp_path: Path
) -> None:
    checksum_file = write_checksum(tmp_path, "invalid content\n")

    result, warnings = verify_downloaded_appimage(
        appimage,
        make_asset(appimage_digest),
        checksum_file,
    )

    assert result.status is VerificationStatus.VERIFIED
    assert result.method == "digest"
    assert len(warnings) == 1
    assert warnings[0].code is WarningCode.CHECKSUM_FILE_CORRUPT


def test_missing_verification_method_returns_missing(appimage: Path) -> None:

    result, warnings = verify_downloaded_appimage(
        appimage,
        make_asset(),
        None,
    )

    assert result.status is VerificationStatus.MISSING
    assert result.method is None
    assert warnings == []


def test_parse_checksum_file_matches_filename_with_spaces() -> None:
    checksum = "b" * 64
    content = f"{checksum}  {APPIMAGE_NAME} with spaces\n"

    assert (
        _parse_checksum_file(content, f"{APPIMAGE_NAME} with spaces")
        == checksum
    )


def test_empty_checksum_file_is_corrupt_warning(
    appimage: Path, tmp_path: Path
) -> None:
    checksum_file = write_checksum(tmp_path, "")

    result, warnings = verify_downloaded_appimage(
        appimage,
        make_asset(),
        checksum_file,
    )

    assert result.status is VerificationStatus.MISSING
    assert len(warnings) == 1
    assert warnings[0].code is WarningCode.CHECKSUM_FILE_CORRUPT


def test_checksum_file_mismatch_fails(appimage: Path, tmp_path: Path) -> None:
    checksum_file = write_checksum(tmp_path, f"{'0' * 64}  {APPIMAGE_NAME}\n")

    result, warnings = verify_downloaded_appimage(
        appimage,
        make_asset(),
        checksum_file,
    )

    assert result.status is VerificationStatus.FAILED
    assert result.method == "checksum_file"
    assert result.expected_hash == "0" * 64
    assert warnings == []


def test_checksum_file_without_target_is_corrupt_warning(
    appimage: Path, appimage_digest: str, tmp_path: Path
) -> None:
    checksum_file = write_checksum(tmp_path, f"{'a' * 64}  other.AppImage\n")

    result, warnings = verify_downloaded_appimage(
        appimage,
        make_asset(),
        checksum_file,
    )

    assert result.status is VerificationStatus.MISSING
    assert len(warnings) == 1
    assert warnings[0].code is WarningCode.CHECKSUM_FILE_CORRUPT


@pytest.mark.parametrize(
    "error",
    [
        OSError("permission denied"),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
    ],
)
def test_unreadable_checksum_file_is_corrupt_warning(
    appimage: Path,
    appimage_digest: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    checksum_file = write_checksum(tmp_path, f"{'a' * 64}  {APPIMAGE_NAME}\n")

    def raise_read_error(*args: object, **kwargs: object) -> str:
        raise error

    monkeypatch.setattr(Path, "open", raise_read_error)

    result, warnings = verify_downloaded_appimage(
        appimage,
        make_asset(),
        checksum_file,
    )

    assert result.status is VerificationStatus.MISSING
    assert len(warnings) == 1
    assert warnings[0].code is WarningCode.CHECKSUM_FILE_CORRUPT


def test_parse_checksum_file_does_not_match_suffix_only() -> None:
    checksum = "a" * 64

    assert (
        _parse_checksum_file(
            f"{checksum}  not-{APPIMAGE_NAME}\n",
            APPIMAGE_NAME,
        )
        is None
    )


def test_oversized_checksum_file_is_corrupt_warning(
    appimage: Path, tmp_path: Path
) -> None:
    # Create a checksum file larger than 1 MiB
    large_content = "a" * (1024 * 1024 + 1)  # 1 MiB + 1 byte
    checksum_file = write_checksum(tmp_path, large_content)

    result, warnings = verify_downloaded_appimage(
        appimage,
        make_asset(),
        checksum_file,
    )

    assert result.status is VerificationStatus.MISSING
    assert len(warnings) == 1
    assert warnings[0].code is WarningCode.CHECKSUM_FILE_CORRUPT
