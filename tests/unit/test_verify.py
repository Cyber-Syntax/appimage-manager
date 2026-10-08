import base64
import hashlib
from pathlib import Path

import pytest
import yaml

from appman.models import Asset, AssetType, VerificationStatus, WarningCode
from appman.verify import (
    _check_hash,
    _decode_base64_sha512,
    _parse_checksum_file,
    _parse_latest_linux_yml,
    verify_downloaded_appimage,
)

GITHUB_DIGEST = (
    "27522206c3973efaebfd38f23f0512b4938ae8b1eb2d7a23a9c0af7e957727fa"
)

DEVELOPER_SHA256 = (
    "c1ccbe4b9e586e0a7358c0c9d06f08322e3eac953b100e6ab6084253a5e2dbfd"
)

DEVELOPER_SHA512 = (
    "712ea8804e5e5a8ff5b1cfb5230dc72dd723fbc9506a8bbccdd0a4a6f5efd08f"
    "926822b852d87814d9f23a3d29f8c933590f5f6d5fc1ef75eb846b21bfb2983c"
)
ELECTRON_SHA512_B64 = "LotnOiMGE6EMIpMuC5Xu1KQF1lAAshdDhEVd6N4PAP5vDozRjNYcmFVReUYZj1t1MPZpWwTWzEfQdF3HSpcbhQ=="

ELECTRON_SHA512_HEX = (
    "2e8b673a230613a10c22932e0b95eed4a405d65000b2174384455de8de0f00fe"
    "6f0e8cd18cd61c9855517946198f5b7530f6695b04d6cc47d0745dc74a971b85"
)


APPIMAGE_NAME = "example.AppImage"


@pytest.fixture
def appimage(tmp_path: Path) -> tuple[Path, str, str]:
    """Create a deterministic AppImage-like file and its hashes."""
    path = tmp_path / APPIMAGE_NAME
    path.write_bytes(b"deterministic AppImage payload")

    content = path.read_bytes()
    # SHA256: 8593582660da4293fe21fe9d2929167a8942d65f3a900e471515fa57772b1536
    # SHA512: 36970338fe27d2c5a01e3ae6e33b1ea20729ee13a09392a425bb15d77fcdb5de6ca2c3bfdb89f2513b66fbd04defc40c7c5c65157e036b78b322c100f255bbf3
    sha256 = hashlib.sha256(content).hexdigest()
    sha512 = hashlib.sha512(content).hexdigest()

    return path, sha256, sha512


def make_asset(
    name: str,
    digest: str | None = None,
) -> Asset:
    return Asset(
        name=name,
        download_url="https://example.com/example.AppImage",
        size=0,
        asset_type=AssetType.APPIMAGE,
        digest=digest,
    )


def test_verify_downloaded_appimage_digest_matches(appimage):
    path, sha256, _ = appimage

    result, warnings = verify_downloaded_appimage(
        path,
        make_asset(APPIMAGE_NAME, digest=sha256),
        None,
    )

    assert result.status is VerificationStatus.VERIFIED
    assert result.method == "digest"
    assert result.expected_hash == sha256
    assert result.actual_hash == sha256
    assert warnings == []


@pytest.mark.parametrize(
    "checksum_content",
    [
        "{hash}  example.AppImage\n",
        "{hash} *./releases/example.AppImage\n",
        "{hash}\n",
    ],
)
def test_verify_downloaded_appimage_checksum_file_matches(
    appimage,
    tmp_path: Path,
    checksum_content: str,
):
    path, sha256, _ = appimage
    checksum_path = tmp_path / "checksums.sha256"
    checksum_path.write_text(
        checksum_content.format(hash=sha256),
        encoding="utf-8",
    )

    result, warnings = verify_downloaded_appimage(
        path,
        make_asset(APPIMAGE_NAME),
        checksum_path,
    )

    assert result.status is VerificationStatus.VERIFIED
    assert result.method == "checksum_file"
    assert result.expected_hash == sha256
    assert result.actual_hash == sha256
    assert warnings == []


def test_verify_downloaded_appimage_mismatch_fails(appimage, tmp_path: Path):
    path, _, _ = appimage
    checksum_path = tmp_path / "checksums.sha256sum"
    checksum_path.write_text(
        f"{'0' * 64}  {APPIMAGE_NAME}\n",
        encoding="utf-8",
    )

    result, warnings = verify_downloaded_appimage(
        path,
        make_asset(APPIMAGE_NAME),
        checksum_path,
    )

    assert result.status is VerificationStatus.FAILED
    assert result.method == "checksum_file"
    assert warnings == []


def test_verify_downloaded_appimage_mismatch_wins_over_passing_digest(
    appimage,
    tmp_path: Path,
):
    path, sha256, _ = appimage
    checksum_path = tmp_path / "checksums.sha256sum"
    checksum_path.write_text(
        f"{'0' * 64}  {APPIMAGE_NAME}\n",
        encoding="utf-8",
    )

    result, warnings = verify_downloaded_appimage(
        path,
        make_asset(APPIMAGE_NAME, digest=sha256),
        checksum_path,
    )

    assert result.status is VerificationStatus.FAILED
    assert result.method == "checksum_file"
    assert warnings == []


def test_verify_downloaded_appimage_corrupt_checksum_warns_but_digest_passes(
    appimage,
    tmp_path: Path,
):
    path, sha256, _ = appimage
    checksum_path = tmp_path / "checksums.sha256"
    checksum_path.write_text("not a checksum\n", encoding="utf-8")

    result, warnings = verify_downloaded_appimage(
        path,
        make_asset(APPIMAGE_NAME, digest=sha256),
        checksum_path,
    )

    assert result.status is VerificationStatus.VERIFIED
    assert result.method == "digest"
    assert [warning.code for warning in warnings] == [
        WarningCode.CHECKSUM_FILE_CORRUPT
    ]


def test_verify_downloaded_appimage_without_verification_data_is_missing(
    appimage,
):
    path, _, _ = appimage

    result, warnings = verify_downloaded_appimage(
        path,
        make_asset(APPIMAGE_NAME),
        None,
    )

    assert result.status is VerificationStatus.MISSING
    assert result.method is None
    assert warnings == []


def test_verify_downloaded_appimage_parses_electron_yaml_checksum(
    appimage,
    tmp_path: Path,
):
    path, _, sha512 = appimage
    checksum_path = tmp_path / "latest-linux.yml"
    checksum_path.write_text(
        yaml.safe_dump(
            {
                "files": [
                    {
                        "url": APPIMAGE_NAME,
                        "sha512": base64.b64encode(
                            bytes.fromhex(sha512)
                        ).decode("ascii"),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result, warnings = verify_downloaded_appimage(
        path,
        make_asset(APPIMAGE_NAME),
        checksum_path,
    )

    assert result.status is VerificationStatus.VERIFIED
    assert result.method == "checksum_file"
    assert warnings == []


@pytest.mark.parametrize(
    "value",
    [
        None,
        123,
        "not-valid-base64",
        base64.b64encode(b"too short").decode("ascii"),
    ],
)
def test_decode_base64_sha512_rejects_invalid_values(value):
    assert _decode_base64_sha512(value) is None


def test_parse_latest_linux_yml_rejects_invalid_yaml():
    assert _parse_latest_linux_yml("[unclosed", APPIMAGE_NAME) is None


def test_parse_latest_linux_yml_rejects_non_mapping_document():
    assert _parse_latest_linux_yml("- one\n- two\n", APPIMAGE_NAME) is None


def test_parse_latest_linux_yml_skips_malformed_entries():
    content = yaml.safe_dump(
        {
            "files": [
                None,
                {"url": 123, "sha512": ELECTRON_SHA512_B64},
                {
                    "url": "other.AppImage",
                    "sha512": ELECTRON_SHA512_B64,
                },
                {
                    "url": APPIMAGE_NAME,
                    "sha512": ELECTRON_SHA512_B64,
                },
            ]
        }
    )

    assert (
        _parse_latest_linux_yml(content, APPIMAGE_NAME) == ELECTRON_SHA512_HEX
    )


def test_parse_latest_linux_yml_returns_none_when_target_is_missing():
    content = yaml.safe_dump(
        {
            "files": [
                {
                    "url": "other.AppImage",
                    "sha512": ELECTRON_SHA512_B64,
                }
            ]
        }
    )

    assert _parse_latest_linux_yml(content, APPIMAGE_NAME) is None


def test_parse_latest_linux_yml_reads_top_level_checksum():
    content = yaml.safe_dump(
        {
            "path": f"releases/{APPIMAGE_NAME}",
            "sha512": ELECTRON_SHA512_B64,
        }
    )

    assert (
        _parse_latest_linux_yml(content, APPIMAGE_NAME) == ELECTRON_SHA512_HEX
    )


def test_parse_checksum_file_skips_invalid_line_and_reads_sha512():
    expected_hash = "a" * 128
    content = f"not a checksum\n{expected_hash} ./releases/{APPIMAGE_NAME}\n"

    assert _parse_checksum_file(content, APPIMAGE_NAME) == expected_hash


def test_check_hash_returns_none_for_unsupported_hash_length(appimage):
    path, _, _ = appimage

    assert _check_hash("digest", path, "unsupported") is None


def test_verify_downloaded_appimage_unreadable_checksum_warns(
    appimage,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    path, _, _ = appimage
    checksum_path = tmp_path / "checksums.sha256"
    checksum_path.write_text("checksum", encoding="utf-8")

    def raise_read_error(self, encoding="utf-8"):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", raise_read_error)

    result, warnings = verify_downloaded_appimage(
        path,
        make_asset(APPIMAGE_NAME),
        checksum_path,
    )

    assert result.status is VerificationStatus.MISSING
    assert [warning.code for warning in warnings] == [
        WarningCode.CHECKSUM_FILE_CORRUPT
    ]


def test_parse_checksum_file_accepts_bare_sha512_hash():
    expected_hash = "a" * 128

    assert (
        _parse_checksum_file(
            expected_hash,
            APPIMAGE_NAME,
        )
        == expected_hash
    )


def test_parse_checksum_file_rejects_bare_hash_with_unsupported_length():
    unsupported_hash = "a" * 40

    assert (
        _parse_checksum_file(
            unsupported_hash,
            APPIMAGE_NAME,
        )
        is None
    )
