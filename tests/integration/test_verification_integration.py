import json
from pathlib import Path

import pytest

import appman.verify as verify_module
from appman.api import _parse_release_asset, parse_asset
from appman.models import Asset, VerificationStatus
from appman.verify import verify_downloaded_appimage

FIXTURES = Path(__file__).parents[1] / "fixtures"

# TODO(next release): add latest-linux.yml after YAML checksum parsing support
# is implemented.


@pytest.mark.integration
@pytest.mark.parametrize(
    ("checksum_file", "appimage_name", "algorithm", "expected_hash"),
    [
        (
            "qownnotes-26.10.2.AppImage.sha256",
            "qownnotes-26.10.2.AppImage",
            "sha256",
            "c1ccbe4b9e586e0a7358c0c9d06f08322e3eac953b100e6ab6084253a5e2dbfd",
        ),
        (
            "qownnotes-26.10.2.AppImage.sha256sum",
            "qownnotes-26.10.2.AppImage",
            "sha256",
            "c1ccbe4b9e586e0a7358c0c9d06f08322e3eac953b100e6ab6084253a5e2dbfd",
        ),
        (
            "qownnotes-26.10.2.AppImage.sha512",
            "qownnotes-26.10.2.AppImage",
            "sha512",
            "712ea8804e5e5a8ff5b1cfb5230dc72dd723fbc9506a8bbccdd0a4a6f5efd08"
            "f926822b852d87814d9f23a3d29f8c933590f5f6d5fc1ef75eb846b21bfb2983c",
        ),
        (
            "qownnotes-26.10.2.AppImage.sha512sum",
            "qownnotes-26.10.2.AppImage",
            "sha512",
            "712ea8804e5e5a8ff5b1cfb5230dc72dd723fbc9506a8bbccdd0a4a6f5efd08"
            "f926822b852d87814d9f23a3d29f8c933590f5f6d5fc1ef75eb846b21bfb2983c",
        ),
        (
            "KeePassXC-2.7.12-x86_64.AppImage.DIGEST",
            "KeePassXC-2.7.12-x86_64.AppImage",
            "sha256",
            "564fe8b751b9ef7aa057e4d3d0b2878db24eaa0f6b1c855c82e699ab0913ae49",
        ),
    ],
)
def test_real_checksum_fixtures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    checksum_file: str,
    appimage_name: str,
    algorithm: str,
    expected_hash: str,
) -> None:
    appimage_path = tmp_path / appimage_name
    appimage_path.write_bytes(b"fixture AppImage payload")

    def return_fixture_hash(_path: Path) -> str:
        return expected_hash

    monkeypatch.setattr(
        verify_module,
        f"_{algorithm}_file",
        return_fixture_hash,
    )

    result, warnings = verify_downloaded_appimage(
        appimage_path,
        Asset(
            name=appimage_name,
            download_url="https://example.com/app.AppImage",
            size=appimage_path.stat().st_size,
            asset_type="AppImage",
            digest=None,
        ),
        FIXTURES / checksum_file,
    )

    assert result.status is VerificationStatus.VERIFIED
    assert result.method == "checksum_file"
    assert result.expected_hash == expected_hash
    assert result.actual_hash == expected_hash
    assert warnings == []


@pytest.mark.integration
def test_neovim_appimage_matches_github_digest() -> None:
    api_fixture = FIXTURES / "neovim_neovim.json"
    appimage_path = FIXTURES / "nvim-linux-x86_64.appimage"

    with api_fixture.open(encoding="utf-8") as file:
        release = json.load(file)

    raw_asset = next(
        asset
        for asset in release["assets"]
        if asset["name"] == "nvim-linux-x86_64.appimage"
    )

    appimage_asset = parse_asset(_parse_release_asset(raw_asset))

    assert appimage_asset.size == appimage_path.stat().st_size
    assert (
        appimage_asset.digest
        == "d429822f6994770e3bb10330e0baf21e72b0afe66e0507cb3c631c1c65f4bf41"
    )

    result, warnings = verify_downloaded_appimage(
        appimage_path,
        appimage_asset,
        None,
    )

    assert result.status is VerificationStatus.VERIFIED
    assert result.method == "digest"
    assert result.actual_hash == appimage_asset.digest
    assert warnings == []
