from pathlib import Path
from unittest.mock import patch

from appman.file import move_verified_appimage
from appman.models import ErrorCode, ErrorKind, PackageError, Stage


def test_move_verified_appimages_moves_file_to_persistent_dir(
    tmp_path: Path,
) -> None:
    src = tmp_path / "cache" / "QOwnNotes.AppImage"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"fake content")

    dest_path = tmp_path / "appimages"

    with patch("appman.file.APPIMAGES_DIR", dest_path):
        result = move_verified_appimage(src, "QOwnNotes")

    dest = dest_path / "QOwnNotes.AppImage"

    assert result == dest
    assert dest.read_bytes() == b"fake content"
    assert not src.exists()  # Ensure the source file has been moved


def test_move_verified_appimages_returns_permission_error(
    tmp_path: Path,
) -> None:
    src = tmp_path / "cache" / "QOwnNotes.AppImage"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"fake content")

    with patch("appman.file.shutil.move", side_effect=PermissionError):
        result = move_verified_appimage(src, "QOwnNotes")

    assert isinstance(result, PackageError)
    assert result.package == "QOwnNotes"
    assert result.code == ErrorCode.PERMISSION_DENIED
    assert result.kind == ErrorKind.FILESYSTEM
    assert result.stage == Stage.INSTALL.value


def test_move_verified_appimage_returns_move_error(tmp_path: Path) -> None:
    src = tmp_path / "cache" / "QOwnNotes.AppImage"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"fake content")

    with patch("appman.file.shutil.move", side_effect=OSError):
        result = move_verified_appimage(src, "QOwnNotes")

    assert isinstance(result, PackageError)
    assert result.package == "QOwnNotes"
    assert result.code == ErrorCode.FILESYSTEM_MOVE_ERROR
    assert result.kind == ErrorKind.FILESYSTEM
    assert result.stage == Stage.INSTALL.value
